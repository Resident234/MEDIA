#!/usr/bin/env python3
"""Collect every shopping organisation 2GIS knows about in Dushanbe.

Same machinery as fitness_2gis/collect_dushanbe.py, which this reuses as
evidence: the demo key resolves exactly one Tajik city (Dushanbe, city_id
70030076174471798), `polygon` restricts strictly, and the ceiling per query
is 5 pages x 10 items — so every query whose total exceeds 50 is collected by
recursive split of the city box until each tile fits.

Query set follows the раздел 8 request: базар/бозор/рынок (bazaars), торговый
центр, супермаркет, гипермаркет, магазин and the Tajik дукон (shops),
интернет-магазин and маркетплейс (online), пункт выдачи (ПВЗ), ремесла and
сувениры (crafts). Rubric-scoped passes anchor the biggest categories, the
rubric ids coming from the facet probe (_facet_probe.json): 350 Супермаркетҳо,
12127 Гипермаркетҳо, 112611 Нуқтаи додани фармоиши интернетӣ (ПВЗ),
110333 Молҳои миллӣ (национальные/ремесленные товары), 510 Тӯҳфаҳо (сувениры).

Outputs (UTF-8 files; the console prints ASCII only):
  items_all.json      every distinct item, fields + passes that found it
  items.tsv           same rows, readable by eye
  collect_report.json per-pass totals, tile statistics, declared totals
"""
from __future__ import annotations

import io
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

KEY = os.environ["TWOGIS_API_KEY"]
HERE = os.path.dirname(os.path.abspath(__file__))
ITEMS = "https://catalog.api.2gis.com/3.0/items"

CITY_ID = "70030076174471798"          # Душанбе г. (Таджикистан)
CITY_ALIAS = "dushanbe"
TJ_WORDS = ("Таджикистан", "Тоҷикистон")

QUERIES = ["базар", "бозор", "рынок", "торговый центр", "супермаркет",
           "гипермаркет", "пункт выдачи", "интернет-магазин", "маркетплейс",
           "ремесла", "сувениры", "магазин", "дукон", "ярмарка"]
RUBRICS = ["350", "12127", "112611", "110333", "510"]

FIELDS = ("items.reviews,items.address_name,items.point,items.adm_div,"
          "items.rubrics,items.address,items.external_content")
PAGE_SIZE = 10
MAX_PAGES = 5
SLEEP = 0.28

ROOT_BBOX = (68.58, 38.42, 69.06, 38.74)   # lon_min, lat_min, lon_max, lat_max
MAX_DEPTH = 7

found: Dict[str, Dict[str, Any]] = {}
report: List[Dict[str, Any]] = []
requests_made = 0


def get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    global requests_made
    for attempt in range(4):
        try:
            response = requests.get(url, params={**params, "key": KEY}, timeout=60)
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


def store(items: List[Dict[str, Any]], pass_name: str) -> None:
    for item in items:
        item_id = item.get("id")
        if not item_id or not in_tajikistan(item):
            continue
        record = found.get(str(item_id))
        if record is None:
            record = dict(item)
            record["_passes"] = []
            found[str(item_id)] = record
        if pass_name not in record["_passes"]:
            record["_passes"].append(pass_name)


def fetch_pages(params: Dict[str, Any], pass_name: str) -> Optional[int]:
    total: Optional[int] = None
    for page in range(1, MAX_PAGES + 1):
        data = get(ITEMS, {**params, "page": page, "page_size": PAGE_SIZE})
        result = data.get("result") or {}
        if total is None:
            total = result.get("total")
        items = result.get("items") or []
        store(items, pass_name)
        if len(items) < PAGE_SIZE:
            break
        time.sleep(SLEEP)
    return total


def wkt(bbox: Tuple[float, float, float, float]) -> str:
    lon_min, lat_min, lon_max, lat_max = bbox
    return "POLYGON((%.6f %.6f, %.6f %.6f, %.6f %.6f, %.6f %.6f, %.6f %.6f))" % (
        lon_min, lat_min, lon_max, lat_min, lon_max, lat_max, lon_min, lat_max,
        lon_min, lat_min,
    )


def total_for(params: Dict[str, Any], pass_name: str) -> Tuple[Optional[int], Optional[int], Any]:
    data = get(ITEMS, {**params, "page": 1, "page_size": PAGE_SIZE})
    meta = data.get("meta") or {}
    result = data.get("result") or {}
    items = result.get("items") or []
    store(items, pass_name)
    return result.get("total"), meta.get("code"), (meta.get("error") or {}).get("type")


def tile_collect(params: Dict[str, Any], bbox: Tuple[float, float, float, float],
                 pass_name: str, depth: int, stats: List[Dict[str, Any]]) -> None:
    total, code, err = total_for(dict(params, polygon=wkt(bbox)), pass_name)
    ceiling = PAGE_SIZE * MAX_PAGES
    if not total:
        stats.append({"bbox": list(bbox), "depth": depth, "code": code,
                      "error": err, "total": total})
        return
    if total > ceiling and depth < MAX_DEPTH:
        lon_min, lat_min, lon_max, lat_max = bbox
        if (lon_max - lon_min) >= (lat_max - lat_min):
            mid = (lon_min + lon_max) / 2
            halves = [(lon_min, lat_min, mid, lat_max), (mid, lat_min, lon_max, lat_max)]
        else:
            mid = (lat_min + lat_max) / 2
            halves = [(lon_min, lat_min, lon_max, mid), (lon_min, mid, lon_max, lat_max)]
        for half in halves:
            tile_collect(params, half, pass_name, depth + 1, stats)
        return
    fetch_pages(dict(params, polygon=wkt(bbox)), pass_name)
    stats.append({"bbox": list(bbox), "depth": depth, "code": code,
                  "total": total, "truncated": total > ceiling})


def city_id_pass(params: Dict[str, Any], pass_name: str) -> Optional[int]:
    """Non-tiled pass scoped by city_id, kept as a cross-check of totals."""
    total: Optional[int] = None
    for page in range(1, MAX_PAGES + 1):
        data = get(ITEMS, {**params, "city_id": CITY_ID, "page": page,
                           "page_size": PAGE_SIZE})
        result = data.get("result") or {}
        if total is None:
            total = result.get("total")
        store(result.get("items") or [], pass_name)
        if len(result.get("items") or []) < PAGE_SIZE:
            break
        time.sleep(SLEEP)
    return total


def main() -> None:
    for query in QUERIES:
        stats: List[Dict[str, Any]] = []
        tile_collect({"q": query, "fields": FIELDS}, ROOT_BBOX,
                     "query:%s" % query, 0, stats)
        declared = city_id_pass({"q": query, "fields": FIELDS},
                                "cityid:%s" % query)
        report.append({"pass": "query:%s" % query, "declared_total": declared,
                       "tiles": stats, "unique_so_far": len(found)})
        print("query done unique=%d tiles=%d requests=%d" % (
            len(found), len(stats), requests_made), flush=True)
        time.sleep(SLEEP)

    for rubric in RUBRICS:
        stats = []
        tile_collect({"rubric_id": rubric, "fields": FIELDS}, ROOT_BBOX,
                     "rubric:%s" % rubric, 0, stats)
        declared = None
        data = get(ITEMS, {"rubric_id": rubric, "city_id": CITY_ID,
                           "page_size": 1, "fields": ""})
        declared = (data.get("result") or {}).get("total")
        report.append({"pass": "rubric:%s" % rubric, "declared_total": declared,
                       "tiles": stats, "unique_so_far": len(found)})
        print("rubric %s done unique=%d tiles=%d requests=%d" % (
            rubric, len(found), len(stats), requests_made), flush=True)
        time.sleep(SLEEP)

    rows: List[Dict[str, Any]] = []
    for item_id, item in found.items():
        rubrics = item.get("rubrics") or []
        district = next((a.get("name") for a in (item.get("adm_div") or [])
                         if a.get("type") == "district"), None)
        reviews = item.get("reviews") or {}
        point = item.get("point") or {}
        rows.append({
            "id": item_id,
            "name": item.get("name"),
            "rating": reviews.get("general_rating", reviews.get("org_rating")),
            "review_count": reviews.get("general_review_count")
                            or reviews.get("org_review_count"),
            "address": item.get("address_name") or item.get("address"),
            "district": district,
            "lon": point.get("lon"),
            "lat": point.get("lat"),
            "rubric_ids": [str(r.get("id")) for r in rubrics],
            "rubric_names": [r.get("name") for r in rubrics],
            "external_content": item.get("external_content"),
            "url_2gis": "https://2gis.tj/%s/firm/%s" % (CITY_ALIAS, item_id),
            "passes": item["_passes"],
        })
    rows.sort(key=lambda r: (r["name"] or ""))
    with io.open(os.path.join(HERE, "items_all.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    with io.open(os.path.join(HERE, "items.tsv"), "w", encoding="utf-8") as fh:
        fh.write("name\taddress\tdistrict\tlat\tlon\trating\treviews\trubrics\turl\n")
        for r in rows:
            fh.write("\t".join(str(x) for x in (
                r["name"], r["address"], r["district"], r["lat"], r["lon"],
                r["rating"], r["review_count"], ";".join(r["rubric_names"] or []),
                r["url_2gis"])) + "\n")
    with io.open(os.path.join(HERE, "collect_report.json"), "w", encoding="utf-8") as fh:
        json.dump({"passes": report, "requests_made": requests_made,
                   "total_items": len(rows)}, fh, ensure_ascii=False, indent=1)
    print("TOTAL items=%d requests=%d" % (len(rows), requests_made), flush=True)


if __name__ == "__main__":
    main()
