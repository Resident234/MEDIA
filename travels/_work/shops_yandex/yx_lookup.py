# -*- coding: utf-8 -*-
"""Look the shopping places named in раздел 8 up on Yandex Maps, by browser.

usage: python yx_lookup.py [max_rows]

Reads `_plan.tsv` — lines `city_slug|query` (a tab also works, the plan file is
hand-written and tabs are easy to lose) — resolves each slug to a city
catalog (`_cityids.json`, filled by yx_cityids.py, plus the catalog used for
Душанбе), runs the search and stores every result card. Already-planned pairs
that have rows in `rows.jsonl` are skipped, so the pass is resumable: the
service throttles long runs, and a restart should not redo finished work.

Per pair we record the outcome kind explicitly — `list`, `org` (the search
resolved to a single card and Yandex opened it), `empty` ("ничего не нашлось")
or `timeout`/`none` — so "the catalog has no card with this name" is a written
answer rather than an absent line.
"""
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from yxd import harvest, show  # noqa: E402

DUSHANBE = "https://yandex.kz/maps/10318/dushanbe/search/{q}/" \
           "?ll=68.787000%2C38.559800&sll=68.787000%2C38.559800&z=12"
EXTRA = {
    "dushanbe": (DUSHANBE, "Душанбе"),
    "khujand": ("https://yandex.kz/maps/10322/khujand/search/{q}/", "Худжанд"),
    "bohtar": ("https://yandex.kz/maps/10319/bohtar/search/{q}/", "Бохтар"),
    "kulob": ("https://yandex.kz/maps/20882/kulob/search/{q}/", "Куляб"),
    "tursunzoda": ("https://yandex.kz/maps/21107/tursunzoda/search/{q}/",
                   "Турсунзаде"),
}
ROWS = os.path.join(HERE, "rows.jsonl")
LOG = os.path.join(HERE, "lookup.log")

# `23:19:28 dushanbe     "\u0411\u0430\u0440\u0430\u043a\u0430\u0442 \u0440\u044b\u043d\u043e\u043a" list     n=4`
LOGRE = re.compile(r'^(?:\d\d:\d\d:\d\d\s+)?(\S+)\s+"(\S(?:[^"]|\\")*)"'
                   r'\s+(\S+)(?:\s+n=(\d+))?$')


def bases():
    table = dict(EXTRA)
    path = os.path.join(HERE, "_cityids.json")
    if os.path.exists(path):
        ids = json.load(io.open(path, encoding="utf-8"))
        for name, got in ids.items():
            cats = (got or {}).get("cats") or []
            if not cats:
                continue
            cid, slug = cats[0].split("/")
            # A catalog found this way is the city's own, so the search must be
            # scoped to it; the geo id we landed on is kept for the record.
            table[slug] = ("https://yandex.kz/maps/%s/%s/search/{q}/" % (cid, slug),
                           name)
    return table


def done_keys():
    """Пары, которые считать готовыми при перезапуске.

    rows.jsonl даёт пары, где хоть что-то нашлось. Отдельно читаем lookup.log:
    `list`/`org`/`empty` — это ответ («в этом каталоге так не называют»), его
    повторять незачем; `none`/`timeout` — страница не отдала результат, такое
    перезапуск пробует снова.
    """
    seen = set()
    if os.path.exists(ROWS):
        for line in io.open(ROWS, encoding="utf-8"):
            d = json.loads(line)
            seen.add((d["city"], d["query"]))
    if os.path.exists(LOG):
        for line in io.open(LOG, encoding="utf-8"):
            m = LOGRE.match(line.rstrip("\n"))
            if not m or m.group(3) == "NOCATALOG":
                continue
            try:
                city, query, kind = (m.group(1), json.loads('"%s"' % m.group(2)),
                                     m.group(3))
            except ValueError:
                continue
            if kind in ("list", "org", "empty"):
                seen.add((city, query))
    return seen


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    table = bases()
    finished = done_keys()
    plan = [(lambda p: (p[0].strip(), p[1].strip()))(re.split(r"\t|\|", l))
            for l in io.open(os.path.join(HERE, "_plan.tsv"), encoding="utf-8")
            if l.strip() and not l.startswith("#")]
    fh = io.open(ROWS, "a", encoding="utf-8", newline="\n")
    log = io.open(LOG, "a", encoding="utf-8", newline="\n")
    worked = 0
    for city, query in plan:
        if (city, query) in finished:
            continue
        if city not in table:
            line = "%-12s %-30s NOCATALOG" % (city, show(query))
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()
            continue
        base, ru = table[city]
        kind, items = harvest(base.format(q=query))
        for it in items:
            fh.write(json.dumps({
                "city": city, "city_ru": ru, "query": query, "kind": kind,
                "id": it.get("id"), "href": it.get("href"),
                "name": it.get("name"), "coords": it.get("coords"),
                "text": (it.get("text") or "")[:400],
            }, ensure_ascii=False) + "\n")
        fh.flush()
        line = "%-12s %-30s %-8s n=%d" % (city, show(query), kind, len(items))
        print(line, flush=True)
        log.write("%s %s\n" % (time.strftime("%H:%M:%S"), line))
        log.flush()
        worked += 1
        if limit and worked >= limit:
            break


if __name__ == "__main__":
    main()
