# -*- coding: utf-8 -*-
"""Build the crawl target list: the 19 hall cards with rating >= 4.0."""
import io
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(io.open(os.path.join(HERE, "ge4_final.json"), encoding="utf-8"))
if isinstance(d, dict):
    items = d.get("items") or d.get("data") or list(d.values())[0]
else:
    items = d

rows = []
for it in items:
    url = it.get("url_2gis") or ""
    m = re.search(r"/firm/(\d+)", url)
    rows.append({
        "id": m.group(1) if m else "",
        "name": (it.get("name_ru") or it.get("name") or "").strip(),
        "address": (it.get("address_ru") or it.get("address") or "").strip(),
        "district": (it.get("district_ru") or it.get("district") or "").strip(),
        "rating": it.get("rating"),
        "reviews": it.get("review_count") or it.get("reviews"),
        "url": url,
    })

rows.sort(key=lambda r: (-(r["rating"] or 0), r["name"]))
io.open(os.path.join(HERE, "web_targets.json"), "w", encoding="utf-8").write(
    json.dumps(rows, ensure_ascii=False, indent=1))
print("targets=%d  with_id=%d" % (len(rows), sum(1 for r in rows if r["id"])))
for r in rows:
    print("%s | %s | %s" % (r["id"], r["rating"], r["name"].encode("ascii", "backslashreplace").decode("ascii")[:38]))
