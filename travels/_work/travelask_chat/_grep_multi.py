# -*- coding: utf-8 -*-
"""Несколько поисков по корпусу сразу, с фильтром по году.

Запуск: python _grep_multi.py <файл_паттернов> <выход> [мин_год]
Файл паттернов: строки вида  имя<TAB>регэкспс  (UTF-8).
Пишет для каждого паттерна заголовок и совпадения (id | дата | автор | текст).
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MSG = os.path.join(HERE, "messages.jsonl")

pat_file = sys.argv[1]
out_path = sys.argv[2]
min_year = sys.argv[3] if len(sys.argv) > 3 else ""

pats = []
for line in io.open(pat_file, encoding="utf-8"):
    line = line.rstrip(u"\n")
    if not line.strip() or line.startswith(u"#"):
        continue
    name, rx = line.split(u"||", 1)
    pats.append((name.strip(), re.compile(rx, re.I)))

hits = dict((n, []) for n, _ in pats)
for line in io.open(MSG, encoding="utf-8"):
    try:
        r = json.loads(line)
    except ValueError:
        continue
    d = r.get("date") or u""
    if min_year:
        parts = d.split(u".")
        if len(parts) < 3 or parts[2][:4] < min_year:
            continue
    t = r.get("text") or u""
    for name, rx in pats:
        if rx.search(t):
            hits[name].append(u"#%s | %s | %s | %s" % (
                r.get("id"), d, r.get("author") or u"",
                re.sub(u"\\s+", u" ", t).strip()))

out = []
for name, _ in pats:
    out.append(u"\n===== %s: %d =====" % (name, len(hits[name])))
    out.extend(hits[name])
io.open(out_path, "w", encoding="utf-8", newline=u"\n").write(
    u"\n".join(out) + u"\n")
print(u", ".join(u"%s=%d" % (n, len(hits[n])) for n, _ in pats).encode(
    "ascii", "replace").decode("ascii"))
