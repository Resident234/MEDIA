# -*- coding: utf-8 -*-
"""Merge the two Yandex Maps result lists, dedupe, parse fields, filter rating >= 4.

usage: python parse.py <out_jsonl> <out_tsv>

Ratings live in the snippet text as "Рейтинг | 4,1 | 17 оценок" (the numeric
badge's aria-label is only rendered in some passes), so everything is parsed
from the flattened text. A record is kept only if it is a real organisation
card (/maps/org/...) with a rating >= MIN_RATING.
"""
import io
import json
import re
import sys

MIN_RATING = 4.0
RATING = re.compile(r"Рейтинг\s*\|\s*(\d+)[,.](\d+)")
REVIEWS = re.compile(r"(\d+)\s*(?:оценок|оценки|отзывов|отзыва)")
HOURS = re.compile(r"(Открыто до [\d:]+|Круглосуточно|Закрыто(?: до [\d:]+)?|Временно закрыто)")

FIELDS = ["rating", "reviews", "hours", "cats", "addr"]


def parse(rec):
    parts = [p.strip() for p in rec.get("text", "").split("|")]
    out = {"rating": None, "reviews": None, "hours": None, "cats": None,
           "addr": None}
    m = RATING.search(rec.get("text", ""))
    if m:
        out["rating"] = float("%s.%s" % (m.group(1), m.group(2)))
    m = REVIEWS.search(rec.get("text", ""))
    if m:
        out["reviews"] = int(m.group(1))
    m = HOURS.search(rec.get("text", ""))
    if m:
        out["hours"] = m.group(1)
    # category line: the first part after the rating block that lists org types
    for p in parts:
        if re.search(r"(зал|клуб|спорт|фитнес|секция|йога|бассейн|танцы|секции)", p, re.I) \
                and "Рейтинг" not in p and out["cats"] is None and "оцен" not in p:
            out["cats"] = p
            break
    for p in parts:
        if re.search(r"(ул\.|просп|наб\.|переулок|мкр|район|Душанбе|г\.|б-р|шоссе|кв\.)", p):
            out["addr"] = p
            break
    return out


def main():
    outj, outtsv = sys.argv[1], sys.argv[2]
    srcs = ["list_gym.jsonl", "list_fitnes.jsonl"]
    merged = {}
    order = []
    for s in srcs:
        for line in io.open(s, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            key = rec.get("id") or rec.get("href")
            if not key:
                continue
            if key not in merged:
                rec["src"] = [s]
                merged[key] = rec
                order.append(key)
            else:
                if s not in merged[key]["src"]:
                    merged[key]["src"].append(s)
                for f, v in rec.items():
                    if not merged[key].get(f) and v:
                        merged[key][f] = v

    rows = []
    for key in order:
        rec = merged[key]
        href = rec.get("href") or ""
        if "/maps/org/" not in href:
            continue
        p = parse(rec)
        rating = p["rating"]
        if rating is None:
            m = re.search(r"Оценка (\d+[.,]\d+)", rec.get("ratingAria") or "")
            if m:
                rating = float(m.group(1).replace(",", "."))
        coords = rec.get("coords") or ""
        lon, lat = (coords.split(",") + ["", ""])[:2]
        rows.append({
            "id": key,
            "name": rec.get("name"),
            "url": "https://yandex.kz" + href,
            "lon": lon, "lat": lat,
            "rating": rating,
            "reviews": p["reviews"],
            "hours": p["hours"],
            "cats": p["cats"],
            "addr": p["addr"],
            "src": "+".join(x.replace("list_", "").replace(".jsonl", "") for x in rec["src"]),
        })
    keep = [r for r in rows if r["rating"] is not None and r["rating"] >= MIN_RATING]
    keep.sort(key=lambda r: (-r["rating"], -(r["reviews"] or 0)))

    cols = ["name", "rating", "reviews", "lon", "lat", "hours", "cats", "addr", "src",
            "url", "id"]

    def dump(path, recs, skip=()):
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\t".join(c for c in cols if c not in skip) + "\n")
            for r in recs:
                fh.write("\t".join("" if r[c] is None else str(r[c])
                                   for c in cols if c not in skip) + "\n")

    # Full union dump (every organisation card seen, rated or not) so the
    # rating filter can be audited instead of trusted.
    dump("all.tsv", sorted(rows, key=lambda r: -(r["rating"] or -1)))

    with io.open(outj, "w", encoding="utf-8", newline="\n") as fh:
        for r in keep:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    dump(outtsv, keep, skip=("id",))
    print("union cards: %d  kept rating>=%.1f: %d  dropped(no rating): %d" %
          (len(rows), MIN_RATING, len(keep),
           sum(1 for r in rows if r["rating"] is None)))
    print("below threshold: %d" % sum(1 for r in rows
                                      if r["rating"] is not None and r["rating"] < MIN_RATING))
    print("no coords: %d" % sum(1 for r in keep if not r["lon"]))


if __name__ == "__main__":
    main()
