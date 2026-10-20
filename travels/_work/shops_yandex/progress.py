# -*- coding: utf-8 -*-
"""Прогресс yx_lookup.py: сколько пар из _plan.tsv уже отработано."""
import io
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "lookup.log")
PLAN = os.path.join(HERE, "_plan.tsv")

LINE = re.compile(r'^(?:\d\d:\d\d:\d\d\s+)?(\S+)\s+"(\S(?:[^"]|\\")*)"'
                  r'\s+(\S+)(?:\s+n=(\d+))?$')


def main():
    plan = []
    bad = 0
    for x in io.open(PLAN, encoding="utf-8"):
        x = x.rstrip("\n")
        if not x.strip() or x.lstrip().startswith("#"):
            continue
        p = x.split("|")
        if len(p) < 2:
            bad += 1
            continue
        plan.append((p[0], p[1]))
    plan_u = sorted(set(plan))
    cities = sorted(set(c for c, _ in plan_u))

    done, kinds, rows, nocat, odd = {}, {}, 0, set(), []
    if os.path.exists(LOG):
        for x in io.open(LOG, encoding="utf-8"):
            m = LINE.match(x.strip())
            if not m:
                if x.strip():
                    odd.append("NOMATCH " + x.strip())
                continue
            try:
                city, query, kind = (m.group(1), json.loads('"%s"' % m.group(2)),
                                     m.group(3))
            except ValueError:
                odd.append("BADJSON " + x.strip())
                continue
            if kind == "NOCATALOG":
                nocat.add(city)
                continue
            done[(city, query)] = kind
            kinds[kind] = kinds.get(kind, 0) + 1
            rows += int(m.group(4) or 0)

    left = [p for p in plan_u if p not in done]
    print("plan unique pairs: %d, answered (list/org/empty): %d, left: %d" % (
        len(plan_u), sum(v for k, v in kinds.items()), len(left)))
    print("kinds: %s" % kinds)
    print("cities with NOCATALOG: %s" % sorted(nocat))
    print("rows buffered: %d" % rows)
    bycity = {}
    for c, q in left:
        bycity[c] = bycity.get(c, 0) + 1
    print("cities in plan: %d, cities with work left: %d" % (len(cities), len(bycity)))
    print("left by city: %s" % sorted(bycity.items(), key=lambda kv: -kv[1]))
    print("plan rows without separator: %d" % bad)
    print("log lines the parser skipped: %d" % len(odd))
    for x in odd[:5]:
        print("  %s" % x.encode("ascii", "backslashreplace").decode("ascii"))
    print("last done cities: %s" % sorted(set(c for c, _ in done))[-6:])


main()
