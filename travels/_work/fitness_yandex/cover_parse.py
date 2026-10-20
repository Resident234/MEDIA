# -*- coding: utf-8 -*-
"""Summarise the outside-Dushanbe Yandex coverage probe.

Reads <city>_gym.jsonl / <city>_fitnes.jsonl (yx_grab output) and, when the
search resolved to a single org card instead of a list, cover_rows.jsonl
(yx_cover output). Per city we dedupe by card id, pull the rating out of the
snippet text, and report how many organisations the catalog gives and how many
of them pass "rating >= 4.0". Console output is ASCII-only.
"""
import glob
import io
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
# The search snippet writes "Рейтинг | 4,1" with a pipe, the card page has no
# pipe at all ("Рейтинг\n3,9"), so the separator is optional.
RATING = re.compile(r"Рейтинг[\s\xa0]*\|?[\s\xa0]*([0-9](?:,[0-9])?)(?![0-9])")
REVIEWS = re.compile(r"(\d+) оценок?")


def rate(text):
    m = RATING.search(text or "")
    return float(m.group(1).replace(",", ".")) if m else None


def main():
    per = {}
    for path in sorted(glob.glob(os.path.join(HERE, "*_gym.jsonl")) +
                       glob.glob(os.path.join(HERE, "*_fitnes.jsonl"))):
        base = os.path.basename(path)
        if base.startswith("list_"):
            continue
        city = base.split("_")[0]
        for line in io.open(path, encoding="utf-8"):
            d = json.loads(line)
            key = d.get("id") or d.get("href")
            if not key:
                continue
            rec = per.setdefault((city, key), {
                "id": d.get("id"), "href": d.get("href"), "name": d.get("name"),
                "coords": d.get("coords"), "rating": rate(d.get("text")),
                "text": d.get("text") or ""})
            if rec["rating"] is None:
                rec["rating"] = rate(d.get("text"))
    if os.path.exists(os.path.join(HERE, "cover_rows.jsonl")):
        for line in io.open(os.path.join(HERE, "cover_rows.jsonl"), encoding="utf-8"):
            d = json.loads(line)
            key = d.get("id") or d.get("href")
            city = d["city"]
            if not key or (city, key) in per:
                continue
            per[(city, key)] = {"id": d.get("id"), "href": d.get("href"),
                                "name": d.get("name"), "coords": d.get("coords"),
                                "rating": rate(d.get("text")),
                                "text": d.get("text") or ""}
    cities = {}
    for (city, key), r in per.items():
        cities.setdefault(city, []).append(r)
    lines = []
    for city in sorted(cities):
        recs = cities[city]
        rated = [r for r in recs if r["rating"] is not None]
        ge = [r for r in rated if r["rating"] >= 4]
        lines.append("%-11s orgs=%-3d rated=%-3d ge4=%-3d  %s" % (
            city, len(recs), len(rated), len(ge),
            "; ".join("%s@%s" % (r["rating"], json.dumps(r["name"], ensure_ascii=True)[:34])
                      for r in sorted(ge, key=lambda x: -x["rating"]))))
        for r in recs:
            print("  %s | %s | %s | %s" % (
                city, json.dumps(r["name"], ensure_ascii=True)[:40],
                r["rating"], (r["href"] or "")[:60]))
    with io.open(os.path.join(HERE, "cover_summary.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join("%s\t%s\t%s" % (c, r["href"], json.dumps(r, ensure_ascii=False))
                           for (c, _), r in sorted(per.items())) + "\n")
    print("\n".join(lines).encode("ascii", "backslashreplace").decode())
    print("total orgs=%d" % len(per))


if __name__ == "__main__":
    main()
