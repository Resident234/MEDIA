# -*- coding: utf-8 -*-
"""По banks_2gis/rows.jsonl: собрать уникальные сети банков (org_name + count).

usage: python network_summary.py
"""
import io
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from make_md import network_of  # reuse

ROWS = os.path.join(HERE, "rows.jsonl")


def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def main():
    nets = Counter()
    org_names_by_net = {}
    for l in io.open(ROWS, encoding="utf-8"):
        r = json.loads(l)
        if not r.get("is_bank"):
            continue
        n = network_of(r)
        nets[n] += 1
        on = (r.get("org_name") or "").strip()
        if on:
            org_names_by_net.setdefault(n, Counter())[on] += 1
    for n, c in nets.most_common():
        orgs = org_names_by_net.get(n, Counter()).most_common(3)
        print("%s\t%d\t" % (a(n), c) + " | ".join(a(o) + "×" + str(k) for o, k in orgs))


if __name__ == "__main__":
    main()
