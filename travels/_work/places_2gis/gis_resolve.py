# -*- coding: utf-8 -*-
"""2ГИС-обход по объектам раздела 6 (места/архитектура/достопримечательности).

usage:
  python gis_resolve.py            # весь список
  python gis_resolve.py 100        # лимит за сеанс
  python gis_resolve.py --retest   # добрать тех, где пусто

Канал: gis_state.search_url('dushanbe', <имя>) + fetch + items_of. Тот же,
что в food_2gis/collect_gis_ssr.py.catalog 2gis.tj фактически содержит
только Душанбе (пути /khujand/, /bohtar/ и пр. редиректят на Алматы),
поэтому это прохождение полезно именно для душанбинских объектов и
немного — для известных POI, заведённых в душанбинском каталоге.
Для прочих (Худжанд, Пенджикент, ГБАО, трасса) результат будет kind=none —
их подберёт Яндекс-прохождение.

Результат: rows.jsonl (одна строка на объект).
"""
import io
import json
import os
import re
import sys
import time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pharma_2gis"))
import gis_state  # noqa: E402

import requests  # noqa: E402

OBJECTS = os.path.join(HERE, "_objects.tsv")
ROWS = os.path.join(HERE, "rows.jsonl")
LOG = os.path.join(HERE, "resolve.log")
CITY = "dushanbe"
SLEEP = 1.2
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0",
                        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                        "Accept-Language": "ru-RU,ru;q=0.8"})


def fetch_page(url):
    """Одна попытка; 404 с телом — это «ничего не нашлось», а не сбой."""
    try:
        r = SESSION.get(url, timeout=(15, 90))
        if r.status_code == 404 and len(r.text) > 20000:
            return "empty", r.text
        if r.status_code == 200 and len(r.text) > 20000 and \
                "captcha" not in r.url:
            return "fresh", r.text
        return "blocked(code=%d,len=%d)" % (r.status_code, len(r.text)), ""
    except requests.RequestException as e:
        return "error(%s)" % type(e).__name__, ""


def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def norm(txt):
    """Нормализация для токерного сравнения имён."""
    if not txt:
        return ""
    txt = txt.lower()
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r"ё", "е", txt)
    txt = re.sub(r"[^a-z0-9\u0430-\u044f\s]", " ", txt)
    return " ".join(txt.split())


def tokens(txt):
    return set(t for t in norm(txt).split() if len(t) >= 3)


def is_plausible(want, got):
    """True если 2ГИС-совпадение реально про то же место.

    Двух-трёхх-словные запросы: Jaccard>=0.5 или containment.
    Однословные: требуем точного совпадения нормализованной формы —
    иначе «Стиль» найдет «Стиль Групп мебель».
    """
    wt, gt = tokens(want), tokens(got)
    if not wt or not gt:
        return False
    if len(wt) == 1:
        nw, ng = norm(want), norm(got)
        # Для однословных запросов — только точное совпадение: иначе
        # «Стиль» ляжет на «Стиль Групп мебель».
        return nw == ng
    if wt <= gt or gt <= wt:
        return True
    inter = len(wt & gt)
    union = len(wt | gt)
    if union and inter * 2 >= union:
        return True
    return False


def load_objects():
    out = []
    for line in io.open(OBJECTS, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        out.append({"file": parts[0], "group": parts[1], "raw": parts[2],
                    "name": parts[3], "slug": parts[4],
                    "city_ru": parts[5], "is_dus": parts[6] == "1"})
    return out


def done_keys(retest=False):
    out = set()
    if not os.path.exists(ROWS):
        return out
    for line in io.open(ROWS, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("kind") == "hit" or not retest:
            out.add((r.get("file"), r.get("group"),
                     (r.get("raw") or "")[:60]))
    return out


def log(msg):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = "[%s] %s\n" % (stamp, msg)
    sys.stdout.write(a(line))
    sys.stdout.flush()
    io.open(LOG, "a", encoding="utf-8").write(line)


def resolve(o):
    q = o["name"]
    url = gis_state.search_url(CITY, q)
    status, body = fetch_page(url)
    if status == "empty":
        # 404 с телом — карточек нет, но сам HTML валидный.
        return {"kind": "none", "total": 0}
    if status != "fresh" or not body:
        # Один ретрай для временных сбоев.
        time.sleep(2.0)
        status, body = fetch_page(url)
        if status != "fresh" or not body:
            return {"kind": "fetch_fail", "error": str(status)[:180]}
    st = gis_state.state_of(body)
    if not st:
        return {"kind": "no_state"}
    items = gis_state.items_of(st)
    total = gis_state.total_of(st)
    if not items:
        return {"kind": "none", "total": total}
    # Берём первую карточку, если имя похоже; иначе ищем похожую
    # в топ-N (5) выдачи.
    best = None
    for iid, d in items[:5]:
        got = d.get("name") or ""
        if is_plausible(q, got):
            best = (iid, d)
            break
    if best is None:
        return {"kind": "nomatch", "total": total,
                "first": (items[0][1].get("name") or "")[:100]}
    iid, d = best
    point = d.get("point") or {}
    return {
        "kind": "hit",
        "id": str(iid),
        "card_name": d.get("name"),
        "address": d.get("address_name"),
        "lon": point.get("lon"),
        "lat": point.get("lat"),
        "rating": d.get("org_rating"),
        "review_count": d.get("org_review_count"),
        "url_2gis": "https://2gis.tj/%s/firm/%s" % (CITY, iid),
        "total": total,
    }


def main():
    retest = "--retest" in sys.argv
    limit = None
    for arg in sys.argv[1:]:
        if arg.isdigit():
            limit = int(arg)
            break
    objs = load_objects()
    done = done_keys(retest=retest)
    log("start: total=%d done=%d retest=%s" % (len(objs), len(done), retest))
    fh = io.open(ROWS, "a", encoding="utf-8", newline="\n")
    worked = hits = 0
    for idx, o in enumerate(objs, 1):
        k = (o["file"], o["group"], o["raw"][:60])
        if k in done:
            continue
        res = resolve(o)
        rec = dict(o)
        rec.update(res)
        rec["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        worked += 1
        if res.get("kind") == "hit":
            hits += 1
        log("[%04d] %s\t%s\t%s" % (
            idx, res.get("kind") or "?",
            o["name"][:50],
            (res.get("card_name") or res.get("error") or "")[:50]))
        time.sleep(SLEEP)
        if limit and worked >= limit:
            break
    fh.close()
    log("finish: worked=%d hits=%d" % (worked, hits))


if __name__ == "__main__":
    main()
