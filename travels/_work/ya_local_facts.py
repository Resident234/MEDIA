# -*- coding: utf-8 -*-
"""Local-only: pull sentences about free limits and org data from the fetched dumps."""
import io
import json
import re

WORDS = ["бесплат", "лимит", "запрос", "ключ", "организ", "справочник", "тариф",
         "сохран", "карт", "геокодер", "PAY", "403", "ограничен"]

out = []
for name in ("ya_docs_dump3.json", "ya_docs_dump2.json", "ya_docs_dump.json"):
    try:
        d = json.load(io.open(name, encoding="utf-8"))
    except Exception as exc:
        out.append("!! %s %s" % (name, exc))
        continue
    for k, v in d.items():
        text = v.get("text") or ""
        if not text:
            continue
        hits = []
        for ch in re.split(r"(?<=[.!?])\s+|\n", text):
            ch = ch.strip()
            if 20 <= len(ch) <= 300 and any(w in ch.lower() for w in WORDS):
                hits.append(ch)
        if not hits:
            continue
        out.append("\n===== %s | %s | %s" % (name, k, v.get("final", "")))
        for h in hits[:14]:
            out.append("   * " + h)

io.open("ya_local_facts.txt", "w", encoding="utf-8").write("\n".join(out))
print("chars=%d" % len("\n".join(out)))
