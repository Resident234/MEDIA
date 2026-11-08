# -*- coding: utf-8 -*-
"""Stage H: локация природных фото из 'Прочее' (только текстовый контекст).

Для каждого природного/местного фото из Прочее просим LLM:
  1) exact  - точное название природного объекта, ЕСЛИ автор сам его назвал
              ("Пик Победы", "Каракольское ущелье"...);
  2) region - иначе примерный кластер расположения, ЕСЛИ автор написал, где он:
              один из 8 канонических регионов;
  3) none   - места в тексте нет (пустой контекст -> остаётся в Прочее).

Валидация: evidence обязан быть дословной цитатой из текста фото; exact-имя
проверяется по совпадению значимых слов с текстом; region обязан совпасть с
каноническим списком. Ledger loc_class.jsonl идемпотентен по id.
Прогон: python -u rescue_location.py "gpt-oss-20b,auto,fusion"
"""
import csv
import io
import json
import os
import sys
import threading

sys.path.insert(0, os.path.abspath(os.path.join("..", "travelask_chat")))
import triage  # noqa: E402

import classify_text as ct  # noqa: E402
from cluster_entities import norm  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CTX = os.path.join(HERE, "photo_ctx.jsonl")
MANIFEST = os.path.join(HERE, "manifest.csv")
VISION = os.path.join(HERE, "vision_class.jsonl")
RESCUE = os.path.join(HERE, "rescue_class.jsonl")
LEDGER = os.path.join(HERE, "loc_class.jsonl")

# кластеры: имя в промпте/литере -> папка назначения (пересекает apply_location)
REGIONS = [
    u"Памирский тракт",
    u"Памирские горы",
    u"Фанские горы",
    u"Гиссарский хребет",
    u"Северный Таджикистан",
    u"Южный Таджикистан",
    u"Восточный Таджикистан",
    u"Душанбе и окрестности",
]
NATURE_CATS = (u"природа", u"место/город", u"достопримечательность")

# стоп-слова конфликтов: если evidence содержит алиас ДРУГОГО региона и не
# содержит алиас названного - ответ противоречит цитате, отклоняем
REGION_ALIASES = {
    u"Памирский тракт": [u"тракт", u"памирск"],
    u"Памирские горы": [u"памир", u"бадахшан", u"гбао", u"хорог", u"мураб",
                        u"рушан", u"ишкашан", u"зоркуль", u"сарез"],
    u"Фанские горы": [u"фанск", u"искандар", u"ашт"],
    u"Гиссарский хребет": [u"гиссар", u"дарваз", u"фалазджон"],
    u"Северный Таджикистан": [u"худжанд", u"пенджикент", u"зафара",
                              u"истикрав", u"северн", u"коньядом"],
    u"Южный Таджикистан": [u"куляб", u"вахш", u"шурооб", u"южн", u"мумин",
                           u"кабади", u"вахабш", u"танзас"],
    u"Восточный Таджикистан": [u"рашт", u"каратегин", u"гарм", u"джирма",
                               u"восточн", u"санглев"],
    u"Душанбе и окрестности": [u"душанбе", u"варзоб", u"микрорайон",
                               u"навои", u"ботаническ", u"нилоу", u"кайрат"],
}

PROMPT = u"""Ты разбираешь ПРИРОДНЫЕ фотографии туристического чата о Таджикистане.
Для каждого фото даны подпись автора и сообщения переписки вокруг него. Нужна
ЛОКАЦИЯ съёмки, которую назвал сам автор (или явно из переписки видно).

Варианты ответа по каждому фото:
- "exact": автор назвал ТОЧНОЕ название природного/географического объекта,
  где сделан кадр (хребет, пик, озеро, ущелье, водопад, сароз и т.п.) -
  например "Пик Победы", "Каракольское ущелье", "озеро Сарез". Верни это
  название в именительной падежной форме.
- "region": точного названия нет, но автор явно написал, где он находится,
  и это относится к одному из канонических кластеров:
  %s.
  Верни название кластера СЛОВНО из списка.
- "none": автор нигде не указал место съёмки (фоновые упоминания городов в
  чужих репликах не считаются).

Ответ - строго JSON-массив, по объекту на фото:
{"n": <номер>, "kind": "exact|region|none", "place": "<название или кластер>",
 "evidence": "<ДОСЛОВНАЯ цитата из текста, подтверждающая место>"}
Для "none" place и evidence - пустые строки. Не додумывай локацию.

%s
"""

ITEM = u"""%d) [%s] автор: %s
   подпись: %s
   до: %s
   после: %s"""


def sig_tokens_match(place, blob):
    """Каждое значимое слово place встречается в blob как основа слова."""
    for t in norm(place).split():
        if len(t) < 4:
            continue
        stem = t[:max(4, len(t) - 1)]
        if not any(e.startswith(stem) or t.startswith(e[:len(stem)])
                   for e in norm(blob).split()):
            return False
    return True


def gather():
    """Фото из Прочее с природной категорией (vision/rescue) или без категории."""
    photos = {}
    for l in io.open(CTX, encoding="utf-8"):
        try:
            r = json.loads(l)
            photos[r["id"]] = r
        except ValueError:
            pass

    def cat_ledger(path):
        d = {}
        if os.path.exists(path):
            for l in io.open(path, encoding="utf-8"):
                try:
                    r = json.loads(l)
                    d[r["id"]] = r.get("category") or u""
                except ValueError:
                    pass
        return d

    vc, rc = cat_ledger(VISION), cat_ledger(RESCUE)
    with io.open(MANIFEST, encoding="utf-8-sig", newline=u"") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        if r["folder"] != u"Прочее":
            continue
        pid = int(r["id"])
        cat = rc.get(pid) or vc.get(pid) or u""
        if cat and cat not in NATURE_CATS:
            continue  # скриншоты, мемы, интерьеры и пр. не локализуем
        p = photos.get(pid)
        if not p:
            continue
        blob = u" ".join([p.get("caption") or u""] + (p.get("ctx_before") or []) +
                         (p.get("ctx_after") or []))
        if not blob.strip():
            continue  # совсем пусто - LLM нечего читать
        out.append({"id": pid, "file": p["file"], "date": p.get("date"),
                    "author": p.get("author"), "caption": p.get("caption"),
                    "blob": blob,
                    "ctx_before": p.get("ctx_before") or [],
                    "ctx_after": p.get("ctx_after") or []})
    return out


def batch_block(rows):
    parts = []
    for k, r in enumerate(rows, 1):
        parts.append(ITEM % (k, r.get("date") or u"?", r.get("author") or u"?",
                             r.get("caption") or u"(без подписи)",
                             u" || ".join(r["ctx_before"] or [u"-"]),
                             u" || ".join(r["ctx_after"] or [u"-"])))
    return PROMPT % (u"; ".join(u"\"%s\"" % x for x in REGIONS),
                     u"\n\n".join(parts))


def validate(row, v):
    kind = (v.get("kind") or u"").strip().lower()
    place = (v.get("place") or u"").strip()
    ev = (v.get("evidence") or u"").strip()
    if kind not in ("exact", "region") or not place or not ev:
        return u"", u""
    if norm(ev) not in norm(row["blob"]):
        return u"", u""  # evidence обязан быть дословной цитатой
    if kind == u"region":
        matched = u""
        for rg in REGIONS:
            if norm(place) == norm(rg) or norm(rg) in norm(place) \
               or norm(place) in norm(rg):
                matched = rg
                break
        if not matched:
            return u"", u""
        nev = norm(ev)
        own = any(a in nev for a in REGION_ALIASES[matched])
        other = [rg for rg in REGIONS if rg != matched
                 and any(a in nev for a in REGION_ALIASES[rg])]
        if other and not own:
            if len(other) == 1:
                matched = other[0]  # цитата однозначно про другой регион
            else:
                return u"", u""
        return u"region", matched
    if not sig_tokens_match(place, row["blob"]):
        return u"", u""
    return u"exact", place


def main():
    models = [m.strip() for m in (sys.argv[1].split(",") if len(sys.argv) > 1
              else triage.MODELS) if m.strip()]
    per = int(os.environ.get("PER", "6"))
    limit = int(os.environ.get("LIMIT", "0"))

    todo_all = gather()
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
    print("nature_photos: %d, todo: %d, already: %d, models: %s, per=%d"
          % (len(todo_all), len(todo), len(todo_all) - len(todo), models, per))

    pool = ct.Pool(models, interval=1.0)
    lock = threading.Lock()
    counter = [0]
    located = [0]

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
                kind, place = validate(r, verdicts[k])
                ev = (verdicts[k].get("evidence") or u"").strip() if place else u""
                recs.append({"id": r["id"], "file": r["file"], "date": r.get("date"),
                             "author": r.get("author"), "caption": r.get("caption"),
                             "kind": kind, "place": place, "evidence": ev,
                             "named": bool(place), "stage": "loc",
                             "model": models[0]})
                if place:
                    located[0] += 1
            with io.open(LEDGER, "a", encoding="utf-8", newline=u"\n") as f:
                for rec in recs:
                    f.write(json.dumps(rec, ensure_ascii=False) + u"\n")
            counter[0] += len(recs)
            print("  %d/%d (located=%d)" % (counter[0], len(todo), located[0]))

    chunks = [todo[i:i + per] for i in range(0, len(todo), per)]
    workers = int(os.environ.get("WORKERS", "2"))
    with ct.ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, chunks))
    print("done located=%d/%d" % (located[0], counter[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
