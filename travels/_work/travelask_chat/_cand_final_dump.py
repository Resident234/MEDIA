# -*- coding: utf-8 -*-
"""Финальный список кандидатов из _cand_final.jsonl -> _cand_final.txt."""
import io
import json
import os

import _cluster_llm as C

OUT = os.path.join(C.HERE, "_cand_final.txt")
lines = []
for r in C.load_jsonl(C.CFINAL):
    lines.append(u"## %s" % r.get("name"))
    lines.append(u"verdict=%s closer=%s strong=%s model=%s" % (
        r.get("verdict"), r.get("closer"), r.get("strong"), r.get("model")))
    lines.append(u"parts: %s" % u", ".join(r.get("parts") or []))
    lines.append(u"scope: %s" % (r.get("scope") or u""))
    lines.append(u"why: %s" % (r.get("why") or u""))
    lines.append(u"risk: %s" % (r.get("risk") or u""))
    lines.append(u"")
io.open(OUT, "w", encoding="utf-8", newline=u"\n").write(u"\n".join(lines))
print("final: %d rows -> %s" % (len(lines), os.path.basename(OUT)))
