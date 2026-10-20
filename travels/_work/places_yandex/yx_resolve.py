# -*- coding: utf-8 -*-
"""Один проход по `_objects.tsv`: для каждого объекта открыть Яндекс-поиск
в каталоге нужного города и снять первую карточку (или сам org-редирект).

usage:
  python yx_resolve.py            # сколько успели, столько и сняли
  python yx_resolve.py 100        # лимит за сеанс
  python yx_resolve.py --retest   # добрать те, где пусто/timeout

Канал: тот же yxd.open_ready(); для lists берём только первую карточку —
наши объекты уникальны, полный список не нужен. Если страница редирекнула
на /maps/org/, это уже карточка.

Сессия по умолчанию: YX_SESSION=yxplaces.

Выход: rows.jsonl (одна строка на объект).
"""
import io
import json
import os
import re
import sys
import time
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import yxd  # noqa: E402

OBJECTS = os.path.join(HERE, "_objects.tsv")
ROWS = os.path.join(HERE, "rows.jsonl")
LOG = os.path.join(HERE, "resolve.log")
# Не гоняем по Яндексу то, что 2ГИС уже закрыл карточкой.
GIS_ROWS = os.path.join(HERE, "..", "places_2gis", "rows.jsonl")

# Первая карточка из виртуализированного списка.
FIRST_ITEM = (
    '(() => {'
    ' const li = document.querySelector("li.search-snippet-view");'
    ' if (!li) return JSON.stringify({name:null, href:null, coords:null});'
    ' const a = li.querySelector("a[href*=\\"/maps/\\"], a[href^=\\"/\\"]");'
    ' const h = li.querySelector(".businesscard-view-title,'
    ' .search-snippet-view-title-line, a, h1, h2, .p6c1e91ec, .d8aae749a");'
    ' const co = li.querySelector("[data-coordinates]");'
    ' const href = a ? (a.href || a.getAttribute("href")) : null;'
    ' const name = h ? h.textContent.trim() : null;'
    ' const coords = co ? co.getAttribute("data-coordinates") : null;'
    ' return JSON.stringify({name, href: href ? href.split("?")[0] : null,'
    ' coords, text: (li.innerText||"").slice(0,300)});})()')


def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


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


def key_for(o):
    return o["file"] + "|" + o["group"] + "|" + o["raw"][:60]


def done_keys(retest=False):
    out = set()
    if not os.path.exists(ROWS):
        return out
    for line in io.open(ROWS, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("kind") in ("org", "list") or not retest:
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
    base = ("https://yandex.kz/maps/%s/search/{q}/" % o["slug"])
    url = base.replace("{q}", quote(o["name"]))
    st = yxd.open_ready(url, budget=180)
    if st is None:
        return {"kind": "timeout"}
    if st.get("org"):
        one = yxd.ev(yxd.ORG)
        return {"kind": "org", "href": one.get("href"),
                "name": one.get("name"), "coords": one.get("coords"),
                "text": one.get("text", "")[:400]}
    if not st.get("snippets"):
        return {"kind": "empty" if st.get("none") else "none"}
    # Тот же harvester, что в прогоне по продуктам/лабораториям, но
    # берём только первую страницу (объект уникален).
    try:
        yxd.ev('window.__yxPass = 0; 1')
        data = yxd.ev(yxd.COLLECT)
    except Exception as e:
        return {"kind": "collect_err", "error": str(e)[:200]}
    items = data.get("items") or []
    if not items:
        return {"kind": "empty"}
    it = items[0]
    href = it.get("href")
    if href and not href.startswith("http"):
        href = "https://yandex.kz" + href
    return {"kind": "list", "href": href, "name": it.get("name"),
            "coords": it.get("coords"), "rating": it.get("ratingAria"),
            "text": (it.get("text") or "")[:400], "n": len(items)}


def gis_hit_keys():
    out = set()
    if not os.path.exists(GIS_ROWS):
        return out
    for line in io.open(GIS_ROWS, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("kind") == "hit":
            out.add((r.get("file"), r.get("group"),
                     (r.get("raw") or "")[:60]))
    return out


def main():
    retest = "--retest" in sys.argv
    force = "--force" in sys.argv
    limit = None
    for arg in sys.argv[1:]:
        if arg.isdigit():
            limit = int(arg)
            break
    objs = load_objects()
    done = done_keys(retest=retest)
    gis_hit = gis_hit_keys() if not force else set()
    log("start: total=%d done=%d gis_hit=%d retest=%s force=%s" % (
        len(objs), len(done), len(gis_hit), retest, force))
    fh = io.open(ROWS, "a", encoding="utf-8", newline="\n")
    worked = ok_count = skipped = 0
    for idx, o in enumerate(objs, 1):
        k = (o["file"], o["group"], o["raw"][:60])
        if k in done:
            continue
        if k in gis_hit:
            skipped += 1
            continue
        res = resolve(o)
        rec = dict(o)
        rec.update(res)
        rec["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        worked += 1
        if res.get("kind") in ("org", "list"):
            ok_count += 1
        log("[%04d] %s\t%s\t%s\t%s" % (
            idx, res.get("kind") or "?", o["slug"],
            o["name"][:60], (res.get("href") or "")[-40:]))
        time.sleep(8.0)
        if limit and worked >= limit:
            break
    fh.close()
    log("finish: worked=%d ok=%d skipped_gis=%d" % (worked, ok_count, skipped))


if __name__ == "__main__":
    main()
