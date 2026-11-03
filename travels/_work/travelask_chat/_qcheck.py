# -*- coding: utf-8 -*-
"""Balanced-guillemet / quote-id audit for the candidates md.

Reports per line: unbalanced « », nested unbalanced pairs, and outermost
quotes that are not followed by a (#id, date) citation. Output UTF-8 file.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else \
    os.path.join(HERE, "..", "..", u"\u0422\u0430\u0434\u0436\u0438\u043a\u0438\u0441\u0442\u0430\u043d_\u043a\u0430\u043d\u0434\u0438\u0434\u0430\u0442\u044b_\u043d\u043e\u0432\u044b\u0445_\u0440\u0430\u0437\u0434\u0435\u043b\u043e\u0432.md")
OUT = os.path.join(HERE, "_qcheck.txt")

txt = io.open(SRC, "r", encoding="utf-8").read()
out = []
for ln, line in enumerate(txt.splitlines(), 1):
    d = 0
    bad = False
    for ch in line:
        if ch == u"\u00ab":
            d += 1
        elif ch == u"\u00bb":
            d -= 1
            if d < 0:
                bad = True
                d = 0
    if d != 0 or bad:
        out.append(u"UNBALANCED %d (depth=%d bad=%d): %s" % (ln, d, bad, line))

# outermost quotes without citation, per whole file
stack = []
spans = []
for i, ch in enumerate(txt):
    if ch == u"\u00ab":
        stack.append(i)
    elif ch == u"\u00bb" and stack:
        st = stack.pop()
        if not stack:
            spans.append((st, i + 1, txt[st + 1:i]))
for st, en, inner in spans:
    if len(inner) < 3:
        continue
    tail = txt[en:en + 260]
    cut = tail.find(u"\u00ab")
    if cut >= 0:
        tail = tail[:cut]
    if not re.search(r"#\d+", tail):
        ln = txt.count("\n", 0, st) + 1
        out.append(u"NOID %d: %s" % (ln, inner[:120]))

io.open(OUT, "w", encoding="utf-8", newline=u"\n").write(u"\n".join(out) + u"\n")
print("written %s (%d lines)" % (os.path.basename(OUT), len(out)))
