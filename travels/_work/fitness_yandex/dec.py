# -*- coding: utf-8 -*-
"""Decode agent-browser eval stdout (a JSON-quoted string) into readable files.

usage: python dec.py <stdout_file> <out_base>
Writes <out_base>.json (structure) and <out_base>_html.txt (if the payload has
an "html" field, which is kept out of the JSON to keep it readable).
"""
import io
import json
import sys

src, outbase = sys.argv[1], sys.argv[2]
s = io.open(src, encoding="utf-8-sig").read().strip()
v = json.loads(s)
if isinstance(v, str):
    v = json.loads(v)
if isinstance(v, dict) and v.get("html"):
    io.open(outbase + "_html.txt", "w", encoding="utf-8").write(v["html"])
    v = dict(v, html="<see %s_html.txt>" % outbase)
io.open(outbase + ".json", "w", encoding="utf-8").write(
    json.dumps(v, ensure_ascii=False, indent=1))
print("ok", outbase)
