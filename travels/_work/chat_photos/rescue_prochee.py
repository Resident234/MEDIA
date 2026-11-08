# -*- coding: utf-8 -*-
"""Stage F: спасение сущностей из 'Прочее' через LLM (вариант A).

Для каждого фото, оставшегося в Прочее (ни text, ни vision не дали имени),
передаём подпись+контекст и КРАТКИЙ список известных сущностей-кандидатов
(отобран подстрочным матчингом по контексту). Модель должна решить: фото
относится ИМЕННО к одной из кандидатов (мимолётное упоминание страны/города
— НЕ основание) либо содержит новое собственное имя.

Валидация (не доверяем LLM на слово):
  - known: выбор обязан совпасть с одним из кандидатов -> нормализуем в его
    точное каноническое написание;
  - new: имя и evidence обязаны встречаться в тексте контекста (норм-подстрок);
    если норма нового имени совпадает с известной сущностью -> переносим в known.

Ledger rescue_class.jsonl идемпотентен по id (перезапуск не тратит квоту).
Прогон: python -u rescue_prochee.py [models]  (PER=8 LIMIT=0 DUMP=1 режимы те же)
"""
import csv
import io
import json
import os
import re
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join("..", "travelask_chat")))
import triage  # noqa: E402

import classify_text as ct  # переиспольпуем call/Pool/last_json_array
from cluster_entities import norm  # та же нормализация

HERE = os.path.dirname(os.path.abspath(__file__))
CTX = os.path.join(HERE, "photo_ctx.jsonl")
MANIFEST = os.path.join(HERE, "manifest.csv")
LEDGER = os.path.join(HERE, "rescue_class.jsonl")

PROMPT = u"""Ты разбираешь фотографии туристического чата о Таджикистане, которые
не удалось отнести к сущностям по подписям и контексту. Для каждого фото даны
подпись, сообщения переписки вокруг него и СПИСОК ИЗВЕСТНЫХ сущностей-кандидатов,
которые где-то мелькают в этом тексте.

Реши по каждому фото, к какой КОНКРЕТНОЙ именованной сущности ОНО ОТНОСИТСЯ:
- "known": фото посвящено одной из кандидатов. Учитывай ТОЛЬКО когда фото про
  саму сущность; мимолётные фоновые упоминания ("Таджикистан", "Душанбе" в
  общем разговоре, название самого чата TravelAsk, ники админов) — НЕ основание.
- "new": в подписи/контексте есть ДРУГОЕ собственное имя (заведение, отель,
  рынок, памятник, природный объект, город, сервис, мероприятие), которого нет
  в кандидатах, и фото относится к нему.
- "none": собственного имени, к которому относится фото, нет.

Ответ — строго JSON-массив, по объекту на фото:
{"n": <номер>, "source": "known|new|none",
 "entity": "<точное название из кандидатов | новое имя | пустая строка>",
 "category": "<заведение|отель|рынок|достопримечательность|место/город|природа|транспорт|скриншот-приложение|карта|еда|люди|интерьер|животное|мем/прочее>",
 "evidence": "<короткая ДОСЛОВНАЯ цитата из текста, на которую опирается ответ>"}
Для "none" entity и evidence — пустые строки. Не выдумывай имена.

%s
"""

ITEM = u"""%d) [%s] автор: %s
   подпись: %s
   до: %s
   после: %s
   кандидаты: %s"""


def load_rows():
    """manifest(Прочее) x photo_ctx -> списки записей с кандидатами."""
    photos = {}
    for l in io.open(CTX, encoding="utf-8"):
        try:
            r = json.loads(l)
            photos[r["id"]] = r
        except ValueError:
            pass
    with io.open(MANIFEST, encoding="utf-8-sig", newline=u"") as f:
        rows = list(csv.DictReader(f))
    known = sorted({r["folder"] for r in rows if r["folder"] != u"Прочее"})
    known_norm = {}
    for k in known:
        n = norm(k)
        if len(n) >= 4:
            known_norm.setdefault(n, k)
    todo = []
    for r in rows:
        if r["folder"] != u"Прочее" or r["stage"] == "service":
            continue
        p = photos.get(int(r["id"]))
        if not p:
            continue
        blob = norm(u" ".join([p.get("caption") or u""] +
                              (p.get("ctx_before") or []) +
                              (p.get("ctx_after") or [])))
        cands = [v for n, v in known_norm.items() if n in blob]
        # сначала более длинные (специфичные) имена, максимум 10
        cands.sort(key=len, reverse=True)
        cands = cands[:10]
        todo.append({"id": p["id"], "file": p["file"], "date": p.get("date"),
                     "author": p.get("author"), "caption": p.get("caption"),
                     "blob": blob, "cands": cands,
                     "ctx_before": p.get("ctx_before") or [],
                     "ctx_after": p.get("ctx_after") or []})
    return todo


def batch_block(rows):
    parts = []
    for k, r in enumerate(rows, 1):
        parts.append(ITEM % (k, r.get("date") or u"?", r.get("author") or u"?",
                             r.get("caption") or u"(без подписи)",
                             u" || ".join(r["ctx_before"] or [u"-"]),
                             u" || ".join(r["ctx_after"] or [u"-"]),
                             u", ".join(r["cands"]) or u"(нет)"))
    return PROMPT % u"\n\n".join(parts)


def validate(row, v):
    """Возвращает (entity, source, category, evidence) после проверки или ('','',...)."""
    src = (v.get("source") or u"").strip()
    ent = (v.get("entity") or u"").strip()
    ev = (v.get("evidence") or u"").strip()
    cat = (v.get("category") or u"").strip()
    if src not in ("known", "new") or not ent:
        return u"", u"none", cat, u""
    ne = norm(ent)
    cands = [(norm(c), c) for c in row["cands"]]
    # совпадение с известной сущностью (в т.ч. вариант "new" про уже известное)?
    for n, k in cands:
        if ne == n:
            return k, u"known", cat, ev
    if src == u"known":
        # допускается вхождение имени кандидата (модель сократила/дописала слово),
        # но каноническим становится точный кандидат
        for n, k in cands:
            if ne in n or n in ne:
                return k, u"known", cat, ev
        return u"", u"none", cat, u""   # галлюцинация мимо кандидатов
    # new: имя и evidence обязаны быть в тексте
    if ne not in row["blob"]:
        return u"", u"none", cat, u""
    if not ev or norm(ev) not in row["blob"]:
        return u"", u"none", cat, u""
    return ent, u"new", cat, ev


def main():
    models = [m.strip() for m in (sys.argv[1].split(",") if len(sys.argv) > 1
              else triage.MODELS) if m.strip()]
    per = int(os.environ.get("PER", "6"))
    limit = int(os.environ.get("LIMIT", "0"))
    dtest = bool(int(os.environ.get("DUMP", "0")))

    todo_all = load_rows()
    done = {}
    if os.path.exists(LEDGER):
        for line in io.open(LEDGER, encoding="utf-8"):
            try:
                done[json.loads(line)["id"]] = True
            except (ValueError, KeyError):
                pass
    todo = [r for r in todo_all if r["id"] not in done]
    if limit:
        todo = todo[:limit]
    print("prochee_photos: %d, todo: %d, already: %d, models: %s, per=%d"
          % (len(todo_all), len(todo), len(todo_all) - len(todo), models, per))
    if dtest and todo:
        print(batch_block(todo[:2]).encode("utf-8", "backslashreplace").decode("utf-8"))
        return 0

    pool = ct.Pool(models, interval=1.0)
    lock = threading.Lock()
    counter = [0]
    rescued = [0]

    def work(chunk):
        arr = None
        for _ in range(5):
            model = pool.pick()
            try:
                arr = ct.last_json_array(
                    ct.call(model, batch_block(chunk), max_tokens=1800, tries=1))
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
        recs = []
        with lock:
            for k, r in enumerate(chunk, 1):
                if k not in verdicts:
                    continue
                ent, src, cat, ev = validate(r, verdicts[k])
                recs.append({"id": r["id"], "file": r["file"], "date": r.get("date"),
                             "author": r.get("author"), "caption": r.get("caption"),
                             "entity": ent, "source": src, "category": cat,
                             "evidence": ev, "named": bool(ent), "stage": "rescue",
                             "model": models[0]})
                if ent:
                    rescued[0] += 1
            with io.open(LEDGER, "a", encoding="utf-8", newline=u"\n") as f:
                for rec in recs:
                    f.write(json.dumps(rec, ensure_ascii=False) + u"\n")
            counter[0] += len(recs)
            print("  %d/%d (rescued=%d)" % (counter[0], len(todo), rescued[0]))

    chunks = [todo[i:i + per] for i in range(0, len(todo), per)]
    workers = int(os.environ.get("WORKERS", "3"))
    with ct.ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, chunks))
    print("done rescued=%d/%d" % (rescued[0], counter[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
