#!/usr/bin/env python3
"""Look the shopping places named in раздел 8 up in the 2GIS catalog.

2GIS knows exactly one Tajik city through this key (Душанбе, city_id
70030076174471798) — see fitness_2gis/coverage.json — so this pass answers the
question "does the directory hold a card for the place the travel articles name,
and what is its link and point".

Two kinds of queries:
  * NAMES  — the proper names taken verbatim from the guide (plus the Tajik
    spelling variants of the day-names, because 2GIS indexes them in Tajik);
    the top few matches per name are kept together with the declared total, so
    "no card for this name" is an evidenced answer rather than a silent miss.
  * CATEGORY — generic words ("базар", "торговый центр", …) to list what the
    catalog really offers in the categories the раздел heading promises.

Every match is required to be in Tajikistan by its adm_div, and Dushanbe
matches are additionally constrained by a polygon, because a bare text query
without spatial restriction happily returns Osh and Khujand cards too.

The key comes only from TWOGIS_API_KEY. Output files are UTF-8; the console is
ASCII because the Windows cp866 console cannot print Tajik.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests

KEY = os.environ.get("TWOGIS_API_KEY")
if not KEY:
    sys.exit("Set TWOGIS_API_KEY")

HERE = os.path.dirname(os.path.abspath(__file__))
ITEMS = "https://catalog.api.2gis.com/3.0/items"
FIELDS = "items.reviews,items.address_name,items.point,items.adm_div,items.rubrics"
PAGE_SIZE = 10
TJ_WORDS = ("Таджикистан", "Тоҷикистон")

# Dushanbe box, same as fitness_2gis/collect_dushanbe.py.
BBOX = (68.58, 38.42, 69.06, 38.74)

NAMES = [line.strip() for line in
         io.open(os.path.join(HERE, "_names.txt"), encoding="utf-8")
         if line.strip()]
# Generic words are listed deeper than the proper-name lookups.
CATEGORY = {"базар", "бозор", "рынок", "торговый центр", "супермаркет",
            "гипермаркет"}
NAME_KEEP = 5
CATEGORY_KEEP = 30

requests_made = 0
rows: List[Dict[str, Any]] = []


def wkt() -> str:
    lon_min, lat_min, lon_max, lat_max = BBOX
    return "POLYGON((%.6f %.6f, %.6f %.6f, %.6f %.6f, %.6f %.6f, %.6f %.6f))" % (
        lon_min, lat_min, lon_max, lat_min, lon_max, lat_max, lon_min, lat_max,
        lon_min, lat_min)


def get(params: Dict[str, Any]) -> Dict[str, Any]:
    global requests_made
    for attempt in range(4):
        try:
            response = requests.get(ITEMS, params={**params, "key": KEY}, timeout=60)
            data = response.json()
        except (requests.RequestException, ValueError):
            time.sleep(2 + 3 * attempt)
            continue
        requests_made += 1
        code = (data.get("meta") or {}).get("code")
        if code in (429, 408):
            time.sleep(15 + 15 * attempt)
            continue
        return data
    return {"meta": {"code": 0, "error": {"type": "network_failed"}}}


def in_tajikistan(item: Dict[str, Any]) -> bool:
    for adm in item.get("adm_div") or []:
        if adm.get("type") == "country" and any(w in (adm.get("name") or "") for w in TJ_WORDS):
            return True
    return False


def city_of(item: Dict[str, Any]) -> Optional[str]:
    return next((a.get("name") for a in item.get("adm_div") or []
                 if a.get("type") == "city"), None)


def district_of(item: Dict[str, Any]) -> Optional[str]:
    return next((a.get("name") for a in item.get("adm_div") or []
                 if a.get("type") == "district"), None)


def one_pass(query: str, keep: int, use_polygon: bool) -> Dict[str, Any]:
    total: Optional[int] = None
    got: List[Dict[str, Any]] = []
    seen_ids = set()
    for page in range(1, keep // PAGE_SIZE + 2):
        params = {"q": query, "fields": FIELDS, "page": page, "page_size": PAGE_SIZE}
        if use_polygon:
            params["polygon"] = wkt()
        data = get(params)
        result = data.get("result") or {}
        if total is None:
            total = result.get("total")
        items = result.get("items") or []
        for item in items:
            if not item.get("id") or item["id"] in seen_ids:
                continue
            seen_ids.add(item["id"])
            got.append(item)
        if len(items) < PAGE_SIZE or len(got) >= keep:
            break
        time.sleep(0.3)
    kept = got[:keep]
    for item in kept:
        point = item.get("point") or {}
        reviews = item.get("reviews") or {}
        rows.append({
            "query": query,
            "kind": "category" if query in CATEGORY else "name",
            "id": item.get("id"),
            "name": item.get("name"),
            "address": item.get("address_name"),
            "city": city_of(item),
            "district": district_of(item),
            "in_tajikistan": in_tajikistan(item),
            "lon": point.get("lon"),
            "lat": point.get("lat"),
            "rating": reviews.get("general_rating"),
            "reviews": reviews.get("general_review_count"),
            "rubrics": [r.get("name") for r in item.get("rubrics") or []],
            "url": "https://2gis.tj/dushanbe/firm/%s" % item.get("id"),
        })
    return {"query": query, "total": total, "kept": len(kept),
            "in_tj": sum(1 for r in rows if r["query"] == query and r["in_tajikistan"])}


def main() -> None:
    summary = []
    for query in NAMES:
        summary.append(one_pass(query, CATEGORY_KEEP if query in CATEGORY else NAME_KEEP,
                                use_polygon=True))
        print(json.dumps(summary[-1], ensure_ascii=True))
    with io.open(os.path.join(HERE, "rows.jsonl"), "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    with io.open(os.path.join(HERE, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump({"passes": summary, "requests": requests_made,
                   "rows": len(rows)}, fh, ensure_ascii=False, indent=1)
    # TSV for reading by eye: only cards that really are in Tajikistan.
    with io.open(os.path.join(HERE, "rows.tsv"), "w", encoding="utf-8") as fh:
        fh.write("query\tkind\tname\tcity\taddress\tdistrict\tlat\tlon\trating\treviews\turl\n")
        for r in rows:
            if not r["in_tajikistan"]:
                continue
            fh.write("\t".join(str(x) for x in (
                r["query"], r["kind"], r["name"], r["city"], r["address"], r["district"],
                r["lat"], r["lon"], r["rating"], r["reviews"], r["url"])) + "\n")
    print("rows=%d in_tj=%d requests=%d" % (
        len(rows), sum(1 for r in rows if r["in_tajikistan"]), requests_made))


if __name__ == "__main__":
    main()
