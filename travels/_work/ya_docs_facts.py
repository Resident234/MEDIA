# -*- coding: utf-8 -*-
"""Extract key/pricing/limits sentences from the fetched Yandex docs dump."""
import io
import json
import re

d = json.load(io.open('ya_docs_dump.json', encoding='utf-8'))
kws = ["ключ", "apikey", "api key", "бесплат", "лимит", "запрос", "сут", "абон",
       "тариф", "passport", "войти", "регистра", "search-maps", "CompanyMetaData",
       "контакт", "телефон", "рейтинг", "ограничен"]

buf = []
for k, v in d.items():
    buf.append("")
    buf.append("######## %s | %s" % (k, str(v.get("final", v.get("error", "")))[:140]))
    text = v.get("text", "")
    if not text:
        continue
    chunks = re.split(r"(?<=[.!?])\s+|\n", text)
    for ch in chunks:
        ch = ch.strip()
        if len(ch) < 15 or len(ch) > 400:
            continue
        low = ch.lower()
        if any(w in low for w in kws):
            buf.append("* " + ch)

io.open('ya_docs_facts.txt', 'w', encoding='utf-8').write("\n".join(buf))
print("sections=%d lines=%d" % (len(d), len(buf)))
