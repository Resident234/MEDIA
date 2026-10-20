# -*- coding: utf-8 -*-
"""Cross-match the Yandex selection against the 2GIS selection by coordinates.

usage: python yx_crossmatch.py  -> crossmatch.tsv + console summary

Both catalogues give coordinates in (lon, lat); a Yandex card and a 2GIS card
within ~120 m of each other are treated as the same building. Names are also
compared (latin/cyrillic-normalised) so a nearby-but-different neighbour is not
merged blindly. The point is to show where the two services disagree on the
rating, and which halls exist only in one of them.
"""
import io
import json
import math
import re

YX_ALL = "../fitness_yandex/all.tsv"
YX_FIN = "../fitness_yandex/final.jsonl"
TG = "../fitness_2gis/items_ru.json"


def norm(s):
    s = (s or "").lower()
    s = s.replace("ё", "е").replace("ъ", "'")
    s = re.sub(r"[^a-zа-я0-9' ]", "", s)
    s = re.sub(r"\b(толори|варзиш[ио]й?|клуби|спортивный|тренажёрный|зал|фитнес[- ]клуб)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


def dist(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, a + b)
    x = (lon2 - lon1) * math.cos((lat1 + lat2) / 2)
    y = lat2 - lat1
    return round(math.hypot(x, y) * 6371000)


def main():
    tg = json.load(io.open(TG, encoding="utf-8"))
    tg_pts = []
    for it in tg:
        if "lon" not in it or "lat" not in it:
            continue
        rev = it.get("reviews_raw") or {}
        tg_pts.append({
            "id": it.get("id"),
            "name": (it.get("name") or "").strip(),
            "lon": it["lon"], "lat": it["lat"],
            "rating": it.get("rating") or rev.get("org_rating"),
            "count": it.get("review_count") or rev.get("org_review_count"),
        })

    yx = {}
    for l in io.open(YX_ALL, encoding="utf-8"):
        c = l.rstrip("\n").split("\t")
        if len(c) < 10 or c[0] == "name":
            continue
        yx[c[-1]] = {"name": c[0], "rating": c[1] or None, "reviews": c[2] or None,
                     "lon": float(c[3]), "lat": float(c[4]), "addr": c[7], "url": c[9]}
    final_ids = {json.loads(l)["id"] for l in io.open(YX_FIN, encoding="utf-8") if l.strip()}

    rows = []
    for yid, y in yx.items():
        best, bd = None, 10 ** 9
        for t in tg_pts:
            d = dist((y["lon"], y["lat"]), (t["lon"], t["lat"]))
            if d < bd:
                best, bd = t, d
        same_name = best and (norm(best["name"]) == norm(y["name"]) or
                              norm(best["name"]) and norm(y["name"]) and
                              (norm(best["name"]) in norm(y["name"]) or norm(y["name"]) in norm(best["name"])))
        rows.append({
            "yandex_id": yid, "yname": y["name"], "yrating": y["rating"],
            "yreviews": y["reviews"], "kept": 1 if yid in final_ids else 0,
            "dist_m": bd, "gis_id": best["id"] if best else None,
            "gname": best["name"] if best else None,
            "grating": best["rating"] if best else None,
            "greviews": best["count"] if best else None,
            "same_name": 1 if same_name else 0,
            "yurl": y["url"],
        })
    rows.sort(key=lambda r: (-r["kept"], r["dist_m"]))
    with io.open("crossmatch.tsv", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\t".join(rows[0].keys()) + "\n")
        for r in rows:
            fh.write("\t".join("" if r[k] is None else str(r[k]) for k in r) + "\n")

    print("2GIS points loaded: %d" % len(tg_pts))
    matched = [r for r in rows if r["dist_m"] <= 120 and r["same_name"]]
    near = [r for r in rows if r["dist_m"] <= 120]
    print("yandex cards: %d, kept(rating>=4): %d" % (len(rows), len(final_ids)))
    print("within 120 m of a 2GIS card: %d (of them name agrees: %d)" % (len(near), len(matched)))
    print("kept rows with no 2GIS twin within 120 m: %d" %
          sum(1 for r in rows if r["kept"] and r["dist_m"] > 120))
    print("kept rows with a 2GIS twin: %d" % sum(1 for r in rows if r["kept"] and r["dist_m"] <= 120))
    for r in rows:
        if r["kept"]:
            print("  %-30s y=%s/%s  %5dm  2gis=%s g=%s/%s samename=%s" % (
                r["yname"].encode("unicode_escape").decode("ascii")[:30], r["yrating"], r["yreviews"],
                r["dist_m"], (r["gname"] or "").encode("unicode_escape").decode("ascii")[:24],
                r["grating"], r["greviews"], r["same_name"]))

    # Reverse direction: does the Yandex keyword collection cover the 19 halls
    # already selected from 2GIS? (keyword search != rubric catalogue)
    rev_lines = []
    ge4 = json.load(io.open("../fitness_2gis/items_full_ge4.json", encoding="utf-8"))
    for it in ge4:
        if "lon" not in it:
            continue
        best, bd = None, 10 ** 9
        for yx_id, y in yx.items():
            d = dist((y["lon"], y["lat"]), (it["lon"], it["lat"]))
            if d < bd:
                best, bd = yx_id, d
        rev_lines.append((it.get("name"), it.get("rating"), it.get("review_count"), bd,
                          best, yx[best]["rating"] if best and bd <= 120 else None,
                          yx[best]["reviews"] if best and bd <= 120 else None))
    with io.open("crossmatch_reverse.tsv", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("gis_name\tg_rating\tg_reviews\tmin_dist_m\tyandex_id\ty_rating\ty_reviews\n")
        for row in rev_lines:
            fh.write("\t".join("" if v is None else str(v) for v in row) + "\n")
    within = [r for r in rev_lines if r[3] <= 120]
    print("2GIS picks: %d, with a Yandex card within 120 m: %d (of those rated >=4 on Yandex: %d)" %
          (len(rev_lines), len(within), sum(1 for r in within if r[5] and float(r[5]) >= 4)))
    for row in rev_lines:
        print("  g=%-46s %s/%s  %5dm  y=%s %s/%s" % (
            str(row[0]).encode("unicode_escape").decode("ascii")[:46], row[1], row[2],
            row[3], row[4], row[5], row[6]))


if __name__ == "__main__":
    main()
