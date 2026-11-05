# -*- coding: utf-8 -*-
"""Stage A: текстовая LLM-классификация фото чата -> именованная сущность.

Для каждого фото по подписи и окрестностям переписки модель ищет СОБСТВЕННОЕ
имя сущности (заведение, отель, рынок, памятник, город, сервис/приложение...).
Общее слово ("горы", "плов") именем не считается -> entity="".

Результат в ledger text_class.jsonl (по id фото; идемпотентно, перезапуск не
тратит квоту).  Тестовый прогон: LIMIT=8 python classify_text.py <models>
"""
import io
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.abspath(os.path.join("..", "travelask_chat")))
import requests  # noqa: E402
import triage    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CTX = os.path.join(HERE, "photo_ctx.jsonl")
LEDGER = os.path.join(HERE, "text_class.jsonl")

PROMPT = u"""Ты разбираешь фотографии из туристического чата о Таджикистане.
Для каждого фото даны подпись автора и короткие сообщения переписки до/после.
Определи, к какой КОНКРЕТНОЙ именованной сущности относится фото — именно
собственное имя (название заведения, отеля, рынка, достопримечательности,
населённого пункта, сервиса/приложения, транспорта, мероприятия). Общее слово
("горы", "плов", "такси") собственным именем НЕ является.

По каждому фото верни объект:
{"n": <номер>, "entity": "<собственное имя или пустая строка>",
 "category": "<заведение|отель|рынок|достопримечательность|место/город|природа|транспорт|скриншот-приложение|карта|еда|люди|интерьер|животное|мем/прочее>",
 "named": <true если entity — собственное имя, иначе false>,
 "evidence": "<короткая цитата из подписи/контекста, давшая имя, или пусто>"}

Не выдумывай имена: если собственного имени в тексте нет, entity="".
Ответ — строго JSON-массив, по одному объекту на фото, без текста вокруг.

%s
"""

ITEM = u"""%d) [%s] автор: %s
   подпись: %s
   до: %s
   после: %s"""


def call(model, prompt, max_tokens=1600, tries=1, image=None):
    content = prompt if image is None else [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + image}}]
    last = u""
    for _ in range(tries):
        try:
            r = requests.post(triage.API_URL,
                              headers={"Authorization": "Bearer " + triage.key(),
                                       "Content-Type": "application/json"},
                              json={"model": model, "temperature": 0,
                                    "max_tokens": max_tokens,
                                    "messages": [{"role": "user", "content": content}]},
                              timeout=420)
            if r.status_code == 200:
                out = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or u""
                if out.strip():
                    return out
                last = u"empty"
            else:
                last = u"HTTP %d %s" % (r.status_code, r.text[:140])
        except Exception as exc:  # noqa: BLE001
            last = u"%s: %s" % (type(exc).__name__, str(exc)[:140])
        time.sleep(3)
    raise RuntimeError(last)


def last_json_array(txt):
    t = re.sub(r"^```[a-zA-Z]*|```$", u"", txt.strip()).strip()
    depth = 0
    start = None
    best = None
    for i, ch in enumerate(t):
        if ch == u"[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == u"]" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    parsed = json.loads(t[start:i + 1])
                except ValueError:
                    continue
                if isinstance(parsed, list):
                    best = parsed
    return best


def load_ledger():
    done = {}
    if os.path.exists(LEDGER):
        for line in io.open(LEDGER, encoding="utf-8"):
            try:
                r = json.loads(line)
                done[r["id"]] = r
            except ValueError:
                pass
    return done


class Pool(object):
    def __init__(self, models, interval=2.0):
        self.models = list(models)
        self.interval = interval
        self.until = dict((m, 0.0) for m in models)
        self.fails = dict((m, 0) for m in models)
        self.lock = threading.Lock()

    def pick(self):
        while True:
            with self.lock:
                now = time.time()
                ready = [m for m in self.models if self.until[m] <= now]
                if ready:
                    m = min(ready, key=lambda x: (self.fails[x], self.until[x]))
                    self.until[m] = now + self.interval
                    return m
                wait = min(self.until.values()) - now
            time.sleep(max(0.4, min(wait, 5)))

    def fail(self, model, cooldown):
        with self.lock:
            self.fails[model] += 1
            self.until[model] = time.time() + cooldown


def batch_block(rows):
    parts = []
    for k, r in enumerate(rows, 1):
        parts.append(ITEM % (k, r.get("date") or u"?", r.get("author") or u"?",
                             r.get("caption") or u"(без подписи)",
                             u" || ".join(r.get("ctx_before") or [u"-"]),
                             u" || ".join(r.get("ctx_after") or [u"-"])))
    return PROMPT % u"\n\n".join(parts)


def main():
    models = [m.strip() for m in (sys.argv[1].split(",") if len(sys.argv) > 1
              else ["gpt-oss-20b", "auto"]) if m.strip()]
    per = int(os.environ.get("PER", "8"))
    limit = int(os.environ.get("LIMIT", "0"))
    dtest = bool(int(os.environ.get("DUMP", "0")))

    rows = [json.loads(l) for l in io.open(CTX, encoding="utf-8")]
    if limit:
        rows = rows[:limit]
    done = load_ledger()
    todo = [r for r in rows if r["id"] not in done]
    print("photos: %d, todo: %d, already: %d, models: %s, per=%d"
          % (len(rows), len(todo), len(rows) - len(todo), models, per))
    if dtest and todo:
        print(batch_block(todo[:3]))
        return 0

    pool = Pool(models, interval=1.0)
    lock = threading.Lock()
    counter = [0]

    def work(chunk):
        arr = None
        for _ in range(5):
            model = pool.pick()
            try:
                arr = last_json_array(call(model, batch_block(chunk), max_tokens=1800, tries=1))
                if arr is not None:
                    break
                pool.fail(model, 20)
            except Exception as exc:  # noqa: BLE001
                pool.fail(model, 120 if u"429" in str(exc) else 25)
        verdicts = {}
        for it in (arr or []):
            if isinstance(it, dict) and isinstance(it.get("n"), int):
                verdicts[it["n"]] = it
        if not verdicts:
            with lock:
                print("  WARN chunk dropped (no JSON), %d photos left todo" % len(chunk))
            return
        with lock:
            with io.open(LEDGER, "a", encoding="utf-8", newline=u"\n") as f:
                for k, r in enumerate(chunk, 1):
                    if k not in verdicts:
                        continue
                    v = verdicts[k]
                    rec = {"id": r["id"], "file": r["file"], "date": r.get("date"),
                           "author": r.get("author"), "caption": r.get("caption"),
                           "entity": (v.get("entity") or u"").strip(),
                           "category": v.get("category") or u"",
                           "named": bool(v.get("named")),
                           "evidence": v.get("evidence") or u"",
                           "stage": "text", "model": models[0]}
                    f.write(json.dumps(rec, ensure_ascii=False) + u"\n")
            counter[0] += len(verdicts)
            print("  %d/%d" % (counter[0], len(todo)))

    chunks = [todo[i:i + per] for i in range(0, len(todo), per)]
    workers = int(os.environ.get("WORKERS", "3"))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, chunks))
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
