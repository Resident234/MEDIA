# -*- coding: utf-8 -*-
"""_peek_ids.py — печатает полный текст сообщений по списку id.
python _peek_ids.py 129132 117703 ...   ->  _route/_peek.txt
Console ASCII, кириллица только в UTF-8 файл.
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MSGS = os.path.join(HERE, "messages.jsonl")
OUT = os.path.join(HERE, "_route", "_peek.txt")

want = set(a for a in sys.argv[1:])
rows = {}
for line in io.open(MSGS, encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    m = json.loads(line)
    if str(m["id"]) in want:
        rows[str(m["id"])] = ((m.get("date") or "")[:10],
                              re.sub(u"\\s+", u" ", m.get("text") or u""))
out = []
for rid in sorted(rows, key=lambda x: int(x)):
    d, t = rows[rid]
    out.append(u"%s | %s | %s" % (rid, d, t))
io.open(OUT, "w", encoding="utf-8", newline="\n").write(u"\n".join(out) + u"\n")
print("peek=%d missing=%d -> _route/_peek.txt"
      % (len(out), len(want) - len(rows)))
