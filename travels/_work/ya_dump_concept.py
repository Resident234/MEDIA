# -*- coding: utf-8 -*-
"""Dump the readable text of the already fetched Yandex org-search docs page."""
import io
import json
import re

d = json.load(io.open("ya_docs_dump.json", encoding="utf-8"))
text = d["geosearch_concept"].get("text", "")
# keep the part that starts at the article body
m = re.search(r"API Поиска по организациям", text)
body = text[m.start():] if m else text
body = re.sub(r"\n{2,}", "\n", body)
io.open("ya_orgapi_concept.txt", "w", encoding="utf-8").write(body)
print("chars=%d lines=%d" % (len(body), body.count("\n") + 1))
