# -*- coding: utf-8 -*-
"""Term-quote normaliser for the candidates md.

Citation gate rule: every «...» must be a verbatim chat quote followed by a
(#id, date). Terms, cluster names and model verdicts are not quotes, so they
are rewritten to `backticks`. Only outermost guillemet spans without a
following #id are touched; quoted chat lines stay untouched.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else \
    os.path.join(HERE, "..", "..",
                 u"\u0422\u0430\u0434\u0436\u0438\u043a\u0438\u0441\u0442\u0430\u043d_"
                 u"\u043a\u0430\u043d\u0434\u0438\u0434\u0430\u0442\u044b_"
                 u"\u043d\u043e\u0432\u044b\u0445_\u0440\u0430\u0437\u0434\u0435\u043b\u043e\u0432.md")

txt = io.open(SRC, "r", encoding="utf-8").read()
stack, spans = [], []
for i, ch in enumerate(txt):
    if ch == u"\u00ab":
        stack.append(i)
    elif ch == u"\u00bb" and stack:
        st = stack.pop()
        if not stack:
            spans.append((st, i, txt[st + 1:i]))

edits = []
for st, en, inner in spans:
    if len(inner) < 3:
        continue
    tail = txt[en + 1:en + 261]
    cut = tail.find(u"\u00ab")
    if cut >= 0:
        tail = tail[:cut]
    if re.search(r"#\d+", tail):
        continue
    if u"`" in inner:
        continue
    edits.append((st, en))

for st, en in reversed(edits):
    txt = txt[:st] + u"`" + txt[st + 1:en] + u"`" + txt[en + 1:]

io.open(SRC, "w", encoding="utf-8", newline=u"\n").write(txt)
print("converted %d term spans" % len(edits))
