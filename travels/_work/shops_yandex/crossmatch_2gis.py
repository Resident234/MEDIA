# -*- coding: utf-8 -*-
"""Cross-match the Yandex shopping rows against the 2GIS array by coordinates.

usage: python crossmatch_2gis.py  -> crossmatch.tsv + console summary

The same method the fitness pass used (nearest neighbour on (lon, lat); names
are compared only as a warning flag, because transliteration differs — the
key is the position). Two differences from that pass: the Yandex array here
is country-wide, while 2GIS knows only Dushanbe — so every Yandex card from
another city is by definition 2GIS-unmatched, and this is reported per city;
and the 2GIS array is large (2016 cards), so a grid index is used instead of
a linear scan. Threshold: 120 m as in the fitness pass, with a note that in
a bazaar/ТЦ one building legitimately holds many organisations.
"""
import io
import json
import math
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
GIS = os.path.join(os.path.dirname(HERE), "shops_2gis", "items_all.json")
YX = os.path.join(HERE, "all.tsv")
THRESH = 120

from make_md import bucket_of  # noqa: E402  та же раскладка по категориям


def norm(s):
    s = (s or "").lower()
    s = s.replace("ё", "е").replace("ъ", "'")
    s = s.replace("ӣ", "и").replace("ҳ", "х").replace("ҷ", "j").replace("ғ", "g")
    return "".join(ch for ch in s if ch.isalnum() or ch in " '")


def name_hit(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0
    return 1 if (a in b or b in a or a == b) else 0


def dist(lon1, lat1, lon2, lat2):
    r1, r2 = math.radians(lat1), math.radians(lat2)
    x = (math.radians(lon2) - math.radians(lon1)) * math.cos((r1 + r2) / 2)
    y = r2 - r1
    return round(math.hypot(x, y) * 6371000)


def main():
    gis = json.load(io.open(GIS, encoding="utf-8"))
    # grid index ~0.002° cells (~200 m at this latitude)
    grid = defaultdict(list)
    pts = []
    for g in gis:
        if g.get("lon") is None or g.get("lat") is None:
            continue
        pts.append(g)
        i = len(pts) - 1
        grid[(int(g["lon"] * 500), int(g["lat"] * 500))].append(i)

    def nearest(lon, lat):
        best, bi = None, None
        cx, cy = int(lon * 500), int(lat * 500)
        for ring in range(0, 4):
            for dx in range(-ring, ring + 1):
                for dy in range(-ring, ring + 1):
                    if ring and max(abs(dx), abs(dy)) != ring:
                        continue
                    for i in grid.get((cx + dx, cy + dy), ()):
                        g = pts[i]
                        d = dist(lon, lat, g["lon"], g["lat"])
                        if best is None or d < best:
                            best, bi = d, g
            if best is not None and best <= THRESH:
                break
        return best, bi

    rows = []
    with io.open(YX, encoding="utf-8") as fh:
        head = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            c = line.rstrip("\n").split("\t")
            if len(c) < len(head):
                c += [""] * (len(head) - len(c))
            r = dict(zip(head, c))
            if not r.get("lat") or not r.get("lon"):
                continue
            city, name, rating = r["city"], r["name"], r["rating"]
            src, prio, url = r.get("src", ""), r.get("priority", ""), r.get("url", "")
            lat, lon = r["lat"], r["lon"]
            d, g = nearest(float(lon), float(lat))
            rows.append({"city": city, "name": name, "rating": rating, "url": url,
                         "lat": float(lat), "lon": float(lon),
                         "dist_m": d if d is not None else "",
                         "gis_name": g["name"] if g else "",
                         "gis_url": g.get("url_2gis", "") if g else "",
                         "gis_rating": "" if not g or g.get("rating") is None else g["rating"],
                         "same_name": name_hit(name, g["name"]) if g else 0,
                         "named": r.get("named", ""),
                         "src": src, "priority": prio})
    with io.open(os.path.join(HERE, "crossmatch.tsv"), "w", encoding="utf-8",
                 newline="\n") as fh:
        cols = ("city", "name", "rating", "dist_m", "same_name", "gis_name",
                "gis_rating", "url", "gis_url", "src", "named", "priority")
        fh.write("\t".join(cols) + "\n")
        for r in rows:
            fh.write("\t".join(str(r[k]) for k in cols) + "\n")

    dush = [r for r in rows if r["city"] == "dushanbe"]
    other = [r for r in rows if r["city"] != "dushanbe"]
    near = [r for r in dush if r["dist_m"] != "" and r["dist_m"] <= THRESH]
    print("yandex cards with coords: total %d, dushanbe %d, other cities %d" %
          (len(rows), len(dush), len(other)))
    print("dushanbe cards with a 2GIS twin <=%dm: %d (name agrees: %d)" %
          (THRESH, len(near), sum(1 for r in near if r["same_name"])))
    prio_near = [r for r in near if r["priority"] == "True"]
    print("priority (key-category) cards with a twin: %d" % len(prio_near))
    named_near = [r for r in dush if r["named"] == "True" and r["dist_m"] != ""
                  and r["dist_m"] <= THRESH]
    print("named-place cards with a twin <=%dm: %d (name agrees: %d)" %
          (THRESH, len(named_near), sum(1 for r in named_near if r["same_name"])))
    bycity = defaultdict(lambda: [0, 0])
    for r in other:
        bycity[r["city"]][0] += 1
    print("per-city yandex cards outside dushanbe (2GIS has no catalog there):")
    for city, (n, _) in sorted(bycity.items()):
        print("  %-30s %d" % (json.dumps(city, ensure_ascii=True)[:30], n))
    dz = sorted((r["dist_m"] for r in dush if r["dist_m"] != ""))
    pct = {"p10": "", "p50": "", "p90": "", "max": ""}
    if dz:
        pct = {"p10": dz[len(dz) // 10], "p50": dz[len(dz) // 2],
               "p90": dz[int(len(dz) * 0.9)], "max": dz[-1]}
        print("nearest-dist percentiles (dushanbe): p10 %s p50 %s p90 %s max %s" %
              (pct["p10"], pct["p50"], pct["p90"], pct["max"]))
    other_by_city = {c: n for c, (n, _) in bycity.items()}

    # Обратное направление: сколько карточек 2ГИС из запрошенных категорий
    # имеют двойника в Яндексе. Массив 2ГИС большой, но Яндекса тут мало,
    # поэтому линейный поиск по нему дешевле сетки.
    yx = [(r["lon"], r["lat"], r) for r in rows]
    back = defaultdict(lambda: [0, 0])
    for g in pts:
        b = bucket_of(g)
        if b is None:
            continue
        best = None
        for lon, lat, r in yx:
            d = dist(g["lon"], g["lat"], lon, lat)
            if d <= THRESH and (best is None or d < best[0]):
                best = (d, r)
        back[b][0] += 1
        if best:
            back[b][1] += 1
    print("reverse: 2GIS category cards having a Yandex twin <=%dm" % THRESH)
    for b in sorted(back):
        n, m = back[b]
        print("  %-38s %4d cards, %3d with twin" % (json.dumps(b, ensure_ascii=True)[:38], n, m))
    tot = [x for x in back.values()]
    print("  TOTAL %d cards, %d with twin" % (sum(x[0] for x in tot), sum(x[1] for x in tot)))

    # Расхождение оценок двух справочников на найденных парах.
    both = [(r, r["gis_rating"]) for r in near
            if r["rating"] and r["gis_rating"] not in ("", None)]
    print("pairs where both catalogs rate it: %d" % len(both))
    disagree = []
    for r, gr in both:
        try:
            diff = abs(float(str(r["rating"]).replace(",", ".")) - float(gr))
        except ValueError:
            continue
        if diff >= 1.0:
            disagree.append((r["name"], r["rating"], gr, r["dist_m"]))
    print("  differ by >=1.0 star: %d" % len(disagree))
    for name, yr, gr, d in sorted(disagree, key=lambda x: -abs(float(str(x[1]).replace(',', '.')) - float(x[2])))[:8]:
        print("    %s : yandex %s vs 2gis %s (%s m)" % (
            json.dumps(name, ensure_ascii=True)[:40], yr, gr, d))

    # Те же числа машиночитаемо: проза раздела «Сверка двух справочников»
    # цитирует их дословно, и после ночного прогона сверить текст с массивом
    # должен один скрипт, а не пересказ по памяти (см. prose_numbers.py).
    stats = {
        "thresh_m": THRESH,
        "yx_with_coords": len(rows),
        "yx_dushanbe": len(dush),
        "yx_other": len(other),
        "dush_twins": len(near),
        "dush_twin_names": sum(1 for r in near if r["same_name"]),
        "prio_twins": len(prio_near),
        "named_twins": len(named_near),
        "named_twin_names": sum(1 for r in named_near if r["same_name"]),
        "percentiles": pct,
        "other_by_city": other_by_city,
        "reverse": {b: [back[b][0], back[b][1]] for b in back},
        "reverse_total": [sum(x[0] for x in tot), sum(x[1] for x in tot)],
        "both_rated": len(both),
        "disagree": [[n, a, b_, d] for n, a, b_, d in disagree],
    }
    with io.open(os.path.join(HERE, "crossmatch_stats.json"), "w",
                 encoding="utf-8", newline="\n") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print("crossmatch_stats.json written")


if __name__ == "__main__":
    main()
