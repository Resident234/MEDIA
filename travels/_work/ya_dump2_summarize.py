# -*- coding: utf-8 -*-
"""Summarise dump2 (products / faq / quickstart / tariffs) and dump texts of interest."""
import io
import json

d = json.load(io.open("ya_docs_dump2.json", encoding="utf-8"))
lines = []
for k, v in d.items():
    if "error" in v:
        lines.append("%-18s ERR %s" % (k, v["error"][:120]))
    else:
        lines.append("%-18s %s text=%d | %s" % (k, v["code"], len(v["text"]), v["final"][:100]))
io.open("ya_dump2_report.txt", "w", encoding="utf-8").write("\n".join(lines) + "\n")

wanted = ["products", "faq", "quickstart", "tariffs", "prices_new", "orgapi_params", "dev_maps_home"]
buf = []
for k in wanted:
    v = d.get(k, {})
    if "text" not in v:
        continue
    buf.append("\n\n=============== %s -> %s\n%s" % (k, v["final"], v["text"]))
io.open("ya_dump2_texts.txt", "w", encoding="utf-8").write("\n".join(buf))
print("\n".join(lines).encode("ascii", "backslashreplace").decode("ascii"))
