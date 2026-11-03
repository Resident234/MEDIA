# -*- coding: utf-8 -*-
"""Быстрый поиск по корпусу для сверки свежих фактов доставки.

Запуск: python _grep_corpus.py <регэкспс> <выход_файл> [год]
Пишет id | дата | автор | текст (полностью), только по сообщениям нужного года.
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MSG = os.path.join(HERE, "messages.jsonl")

pat = sys.argv[1]
if pat.startswith(u"pat:"):
    pat = io.open(pat[4:], encoding="utf-8").read().strip()
out_path = sys.argv[2]
year = sys.argv[3] if len(sys.argv) > 3 else ""
rx = re.compile(pat, re.I)
out = []
n = 0
for line in io.open(MSG, encoding="utf-8"):
    try:
        r = json.loads(line)
    except ValueError:
        continue
    d = (r.get("date") or u"")
    if year:
        parts = d.split(u".")
        if len(parts) < 3 or parts[2][:4] != year:
            continue
    t = r.get("text") or u""
    if not rx.search(t):
        continue
    n += 1
    out.append(u"#%s | %s | %s | %s" % (r.get("id"), d,
                                        r.get("author") or u"",
                                        re.sub(u"\\s+", u" ", t).strip()))
io.open(out_path, "w", encoding="utf-8", newline=u"\n").write(
    u"\n".join(out) + u"\n")
print("matches=%d -> %s" % (n, os.path.basename(out_path)))
