# -*- coding: utf-8 -*-
"""Stage K: vision-разбор фото, оставшихся в 'Прочее'.

Для каждого файла из Прочее шлём картинку vision-модели (как Stage B) и
спрашиваем: что в кадре, категория, ПРИРОДНОЕ ли это, точное название (только
если имя видно в кадре - вывеска/надпись) и примерный регион-кластер по типу
ландшафта (один из 8 канонических) с уверенностью.

accept (валидация на стороне классификатора):
  exact    - kind=exact и есть текст в кадре;
  region   - kind=region, кластер из списка, confidence high|medium;
  priroda  - nature=true, но локация недоступна;
  none     - не природа (скриншот, еда, люди...) - остаётся в Прочее.
Ledger vision_prochee.jsonl идемпотентен по id; непристучавшиеся фото не
пишем (повторный прогон доберёт). Прогон: python -u vision_prochee.py "модели"
"""
import base64
import io
import json
import os
import re
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join("..", "travelask_chat")))
import requests  # noqa: E402
import triage    # noqa: E402

from apply_location import OTHER  # "Прочее"
from cluster_entities import norm  # noqa: E402
from rescue_location import REGIONS, sig_tokens_match

HERE = os.path.dirname(os.path.abspath(__file__))
TRAVELS = os.path.abspath(os.path.join(HERE, "..", ".."))
ROOT = os.path.join(TRAVELS, u"Фото_сущности")
LEDGER = os.path.join(HERE, "vision_prochee.jsonl")
MANIFEST = os.path.join(HERE, "manifest.csv")

PROMPT = u"""Ты смотришь на фотографию из туристического чата о Таджикистане.
Определи, что на ней и где это может быть.

Ответ - строго JSON без текста вокруг:
{"what": "<что в кадре, одно предложение>",
 "category": "<природа|место/город|достопримечательность|заведение|отель|рынок|транспорт|скриншот-приложение|карта|еда|люди|интерьер|животное|мем/прочее|документ>",
 "nature": <true только для природных мест и объектов: горы, озёра, ущелья, реки, водопады, каньоны, плато и пр.>,
 "kind": "<exact|region|none>",
 "place": "<для exact - название объекта, если он прочитывается прямо в кадре (вывеска, надпись на фото); для region - ОДИН кластер дословно из списка: %s; иначе пустая строка>",
 "confidence": "<high|medium|low - насколько уверен в регионе>",
 "text_in_photo": "<дословный текст/надпись, видимая в кадре, или пустая строка>",
 "evidence": "<по чему определял: ландшафт/высота/растительность/надпись>"}

Для landscape-догадки: высокогорная пустынность, серо-коричневые хребты без
леса, голубые озёра-каракули - скорее Памирские горы / Памирский тракт;
зелёные ельники и глубокие ущелья - Фанские горы; жёсткие полупустынные
хребты ближе к столице - Гиссарский хребет; городская застройка - Душанбе и
окрестности. Не выдумывай точные названия - exact ТОЛЬКО если имя видно в кадре.
""" % (u"; ".join(u"\"%s\"" % x for x in REGIONS),)


def load_ledger():
    out = set()
    if os.path.exists(LEDGER):
        for line in io.open(LEDGER, encoding="utf-8"):
            try:
                out.add(json.loads(line)["id"])
            except (ValueError, KeyError):
                pass
    return out


def vcall(model, prompt, b64, max_tokens=500):
    content = [{"type": "text", "text": prompt},
               {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}]
    r = requests.post(triage.API_URL,
                      headers={"Authorization": "Bearer " + triage.key(),
                               "Content-Type": "application/json"},
                      json={"model": model, "temperature": 0,
                            "max_tokens": max_tokens,
                            "messages": [{"role": "user", "content": content}]},
                      timeout=300)
    if r.status_code != 200:
        raise RuntimeError(u"HTTP %d %s" % (r.status_code, r.text[:140]))
    return ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or u""


def json_or_none(txt):
    m = re.search(r"\{.*\}", txt or u"", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


def s(x):
    """Модели иногда отдают список вместо строки - сводим к тексту."""
    if x is None:
        return u""
    if isinstance(x, (list, tuple)):
        return u" ".join(s(i) for i in x).strip()
    if not isinstance(x, str):
        x = u"%s" % (x,)
    return x.strip()


def decide(o):
    """Валидация ответа модели -> accept без галлюцинаций."""
    kind = s(o.get("kind")).lower()
    place = s(o.get("place"))
    conf = s(o.get("confidence")).lower()
    nature = bool(o.get("nature"))
    tip = s(o.get("text_in_photo"))
    if kind == u"exact" and place and tip \
       and sig_tokens_match(place, u"%s %s" % (tip, s(o.get("what")))):
        return u"exact", place
    if kind == u"region" and place and conf in ("high", "medium"):
        for rg in REGIONS:
            if norm(place) == norm(rg):
                return u"region", rg
    if nature:
        return u"priroda", u""
    return u"none", u""


def main():
    models = [m.strip() for m in (sys.argv[1].split(",") if len(sys.argv) > 1
              else triage.MODELS) if m.strip()]
    limit = int(os.environ.get("LIMIT", "0"))
    todo_all = []
    with io.open(MANIFEST, encoding="utf-8-sig", newline=u"") as f:
        import csv
        for r in csv.DictReader(f):
            if r["folder"] != OTHER:
                continue
            base = os.path.basename(r["file"])
            path = os.path.join(ROOT, OTHER, base)
            if os.path.exists(path):
                todo_all.append({"id": int(r["id"]), "file": base, "path": path,
                                 "date": r.get("date"), "author": r.get("author"),
                                 "caption": r.get("caption")})
    done = load_ledger()
    todo = [t for t in todo_all if t["id"] not in done]
    already = len(todo_all) - len(todo)
    if limit:
        todo = todo[:limit]
    print("prochee_files=%d todo=%d already=%d models=%s"
          % (len(todo_all), len(todo), already, models))

    lock = threading.Lock()
    counter = [0]
    acc = {"exact": 0, "region": 0, "priroda": 0, "none": 0}
    percd = {}
    COOLDOWN = 120

    def wait_next():
        while True:
            now = time.time()
            ready = [m for m in models if now >= percd.get(m, 0)]
            if ready:
                return ready
            time.sleep(2)

    def work(t):
        b64 = base64.b64encode(open(t["path"], "rb").read()).decode()
        obj = None
        used = None
        for _round in range(3):
            for m in wait_next():
                try:
                    txt = vcall(m, PROMPT, b64)
                except Exception as exc:  # noqa: BLE001
                    s = str(exc)
                    if u"429" in s or u"vision" in s or u"rate" in s or u"exhaust" in s:
                        percd[m] = time.time() + COOLDOWN
                    time.sleep(1)
                    continue
                o = json_or_none(txt)
                if o is not None:
                    obj, used = o, m
                    break
            if obj is not None:
                break
        if obj is None:
            with lock:
                print("  WARN no-JSON id=%d (повтор доберёт)" % t["id"])
            return
        try:
            _record(t, obj, used)
        except Exception as exc:  # noqa: BLE001
            with lock:
                print("  WARN bad-answer id=%d %s (повтор доберёт)"
                      % (t["id"], type(exc).__name__))

    def _record(t, obj, used):
        accept, place = decide(obj)
        rec = {"id": t["id"], "file": t["file"], "date": t.get("date"),
               "author": t.get("author"), "caption": t.get("caption"),
               "what": s(obj.get("what")), "category": s(obj.get("category")),
               "nature": bool(obj.get("nature")), "kind": s(obj.get("kind")),
               "place": place, "confidence": s(obj.get("confidence")),
               "text_in_photo": s(obj.get("text_in_photo")),
               "evidence": s(obj.get("evidence")),
               "accept": accept, "stage": "vision_prochee", "model": used}
        try:
            json.dumps(rec, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            with lock:
                print("  WARN bad-rec id=%d %s" % (t["id"], exc))
            return
        with lock:
            with io.open(LEDGER, "a", encoding="utf-8", newline=u"\n") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + u"\n")
            counter[0] += 1
            acc[accept] += 1
            if counter[0] % 10 == 0:
                print("  %d/%d exact=%d region=%d priroda=%d none=%d"
                      % (counter[0], len(todo), acc["exact"], acc["region"],
                         acc["priroda"], acc["none"]))

    workers = int(os.environ.get("WORKERS", "2"))
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, todo))
    print("done vision_prochee=%d exact=%d region=%d priroda=%d none=%d"
          % (counter[0], acc["exact"], acc["region"], acc["priroda"], acc["none"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
