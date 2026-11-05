# -*- coding: utf-8 -*-
"""Stage B: vision-доклассификация фото, где текст не дал собственного имени.

Модель с картинкой ищет собственное имя, ВИДИМОЕ на фото (вывеска, логотип,
узнаваемый объект), либо подсказанное подписью/контекстом. Пишет в
vision_class.jsonl (идемпотентно по id). Vision-роут троттлится, поэтому
фильтр: только фото без именованной сущности из Stage A. ENV: LIMIT, SCOPE
('unnamed' — без имени из текста; 'blind' — вообще без подписи и контекста).
"""
import base64
import io
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.abspath(os.path.join("..", "travelask_chat")))
import requests  # noqa: E402
import triage    # noqa: E402
from classify_text import last_json_array  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT = os.path.abspath(os.path.join(HERE, "..", "..",
                     u"Таджикистан \U0001F1F9\U0001F1EF Чат TravelAsk"))
LEDGER = os.path.join(HERE, "vision_class.jsonl")

PROMPT = u"""Ты смотришь на фотографию из туристического чата о Таджикистане.
Определи, к какой КОНКРЕТНОЙ именованной сущности она относится: собственное
название заведения/отеля/рынка/достопримечательности/места/сервиса/памятника,
которое ВИДНО на фото (вывеска, логотип, характерный объект) или следует из
подписи/контекста. Общее слово ("горы", "еда") — не имя.

Подпись автора: {caption}
Контекст до: {before}
Контекст после: {after}

Ответ — строго JSON без текста вокруг:
{{"entity": "<собственное имя или пустая строка>", "category": "<заведение|отель|рынок|достопримечательность|место/город|природа|транспорт|скриншот-приложение|карта|еда|люди|интерьер|животное|мем/прочее>", "named": <true/false>, "evidence": "<что дало имя: вывеска/логотип/подпись/контекст>"}}
"""


def vcall(model, prompt, b64, max_tokens=400, tries=1):
    content = [{"type": "text", "text": prompt},
               {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}]
    last = u""
    for _ in range(tries):
        try:
            r = requests.post(triage.API_URL,
                              headers={"Authorization": "Bearer " + triage.key(),
                                       "Content-Type": "application/json"},
                              json={"model": model, "temperature": 0, "max_tokens": max_tokens,
                                    "messages": [{"role": "user", "content": content}]},
                              timeout=300)
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


def load(path):
    out = {}
    if os.path.exists(path):
        for line in io.open(path, encoding="utf-8"):
            try:
                r = json.loads(line)
                out[r["id"]] = r
            except (ValueError, KeyError):
                pass
    return out


def main():
    models = [m.strip() for m in (sys.argv[1].split(",") if len(sys.argv) > 1
              else ["gemini-2.5-flash-lite"]) if m.strip()]
    scope = os.environ.get("SCOPE", "unnamed")
    limit = int(os.environ.get("LIMIT", "0"))

    photos = [json.loads(l) for l in io.open(os.path.join(HERE, "photo_ctx.jsonl"), encoding="utf-8")]
    texts = load(os.path.join(HERE, "text_class.jsonl"))
    done = load(LEDGER)

    def has_name(pid):
        t = texts.get(pid) or {}
        return t.get("named") and (t.get("entity") or "").strip()

    todo = []
    for p in photos:
        if p.get("type") == "service" or p["id"] in done:
            continue
        if scope == "blind":
            if p.get("caption") or p.get("ctx_before") or p.get("ctx_after"):
                continue
        else:  # unnamed
            if has_name(p["id"]):
                continue
        todo.append(p)
    if limit:
        todo = todo[:limit]
    print("scope=%s photos to vision: %d" % (scope, len(todo)))

    lock = threading.Lock()
    counter = [0]
    skipped = [0]
    state = {"until": 0.0, "fails": 0}

    def work(p):
        while time.time() < state["until"]:
            time.sleep(2)
        src = os.path.join(EXPORT, p["file"].replace("photos/", u"photos" + os.sep))
        if not os.path.exists(src):
            return
        b64 = base64.b64encode(open(src, "rb").read()).decode()
        prompt = PROMPT.format(caption=p.get("caption") or u"(нет)",
                               before=u" | ".join(p.get("ctx_before") or [u"-"])[:600],
                               after=u" | ".join(p.get("ctx_after") or [u"-"])[:600])
        obj = None
        for _ in range(4):
            try:
                obj = json_or_none(vcall(models[0], prompt, b64, tries=1))
                if obj is not None:
                    break
            except Exception as exc:  # noqa: BLE001
                if u"429" in str(exc) or u"vision" in str(exc) or u"cooldown" in str(exc):
                    state["until"] = time.time() + 90
                    state["fails"] += 1
                time.sleep(5)
        # obj is None значит вызовы упались (троттл/ошибка): НЕ пишем —
        # фото останется в todo для повтора, ledger не пачкаем.
        if obj is None:
            with lock:
                skipped[0] += 1
            return
        with lock:
            with io.open(LEDGER, "a", encoding="utf-8", newline=u"\n") as f:
                f.write(json.dumps({"id": p["id"], "file": p["file"], "date": p.get("date"),
                                    "author": p.get("author"), "caption": p.get("caption"),
                                    "entity": (obj.get("entity") or u"").strip(),
                                    "category": obj.get("category") or u"",
                                    "named": bool(obj.get("named")),
                                    "evidence": obj.get("evidence") or u"",
                                    "stage": "vision", "model": models[0]},
                                   ensure_ascii=False) + u"\n")
            counter[0] += 1
            if counter[0] % 20 == 0:
                print("  %d/%d (vision, fails=%d, skipped=%d)"
                      % (counter[0], len(todo), state["fails"], skipped[0]))

    def json_or_none(txt):
        import re
        m = re.search(r"\{.*\}", txt or u"", re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=1) as ex:   # 1 поток: деликатный vision-роут
        list(ex.map(work, todo))
    print("done vision:", counter[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
