# -*- coding: utf-8 -*-
"""Список уникальных org_name из is_bank строк с числом вхождений."""
import io
import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = os.path.join(HERE, "rows.jsonl")

def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")

c = Counter()
for l in io.open(ROWS, encoding="utf-8"):
    r = json.loads(l)
    if not r.get("is_bank"):
        continue
    on = (r.get("org_name") or "").strip()
    if not on:
        on = (r.get("name") or "").strip()
    if on:
        c[on] += 1

# org_name может быть длинным, но для уникализации достаточно 1-го слова сети.
for name, n in c.most_common():
    print("%3d\t%s" % (n, a(name)))
