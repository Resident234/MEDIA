#!/usr/bin/env python3
"""Collect every fitness organisation 2GIS knows about in Tajikistan.

What the probes proved (see coverage.json, probe_cityid.json, probe_facet.txt):

  * Dushanbe is the only Tajik city in the 2GIS catalog reachable through the
    Places API. A polygon over the whole Tajikistan bounding box facets into
    exactly one Tajik city (Душанбе г. (Таджикистан)); reverse geocoding points
    inside Khujand, Kulob or Bokhtar returns only the oblast, and city_id/polygon
    searches there answer 404 itemNotFound.
  * `city_id` + `rubric_id` works and, because each rubric holds <= 56 items, a
    rubric-scoped pass stays under the demo-key ceiling (page <= 5, page_size <= 10).
  * `polygon` restricts strictly, so a text query whose total exceeds 50 is
    collected by recursive quadtree tiling until each tile fits the ceiling.

Outputs (UTF-8 files; the Windows console cannot print Tajik):
  items_all.json  every distinct item with the fields we asked for
  items_ge4.json  rating >= 4.0 subset, sorted by rating
  collect_report.json  per-pass totals, tile statistics, contact-field probe result
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
BYID = "https://catalog.api.2gis.com/3.0/items/byid"

CITY_ID = "70030076174471798"          # Душанбе г. (Таджикистан)
CITY_ALIAS = "dushanbe"
TJ_WORDS = ("Таджикистан", "Тоҷикистон")

QUERIES = ["Фитнес", "Тренажерный зал"]
RUBRICS = ["267", "268", "51256", "20228"]   # залы, фитнес-клубы, секции, йога

FIELDS = "items.reviews,items.address_name,items.point,items.adm_div,items.rubrics"
PAGE_SIZE = 10
MAX_PAGES = 5
SLEEP = 0.28
RATING_MIN = 4.0

# Generous Dushanbe box: the city spans about 68.70-68.92 E / 38.48-38.65 N.
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
    """Paginate one query under the demo ceiling; return the declared total."""
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


def probe_contacts(ids: List[str]) -> Dict[str, Any]:
    """Check every documented way this key could expose phones/messengers.

    Three variants: the full contact field list, a bare card fetch (no fields),
    and the byphone reverse lookup. Each answer is recorded verbatim (code and
    error type) so the conclusion "contacts are not licensed to this key" is
    backed by evidence rather than by absence.
    """
    probes: Dict[str, Any] = {}
    if not ids:
        return probes
    variants = {
        "with_contact_fields": {
            "ids": ",".join(ids[:20]),
            "fields": "items.phones,items.contacts,items.contact_groups,items.urls,items.work_time",
        },
        "bare": {"ids": ",".join(ids[:20])},
        "reviews_only": {"ids": ",".join(ids[:20]), "fields": "items.reviews,items.rubrics"},
    }
    for name, params in variants.items():
        data = get(BYID, params)
        meta = data.get("meta") or {}
        items = (data.get("result") or {}).get("items") or []
        keys = sorted({k for item in items for k in item.keys()})
        probes[name] = {
            "code": meta.get("code"),
            "error": (meta.get("error") or {}).get("type"),
            "n_items": len(items),
            "item_keys": keys,
            "contacts_present": [k for k in keys if k in
                                 ("phones", "contacts", "contact_groups", "urls")],
        }
    data = get(ITEMS, {"q": "+992", "byphone": "99244000000", "page_size": 1})
    probes["byphone"] = {"code": (data.get("meta") or {}).get("code"),
                         "error": ((data.get("meta") or {}).get("error") or {}).get("type")}
    return probes


def rating_of(item: Dict[str, Any]) -> Optional[float]:
    return (item.get("reviews") or {}).get("general_rating")


def main() -> None:
    # Pass 1: rubric-scoped over the Dushanbe box, tiled when a rubric exceeds
    # the ceiling (rubric 267 declares 56 items, i.e. more than 5 pages of 10).
    for rubric in RUBRICS:
        stats: List[Dict[str, Any]] = []
        tile_collect({"rubric_id": rubric, "fields": FIELDS},
                     ROOT_BBOX, "rubric:%s" % rubric, 0, stats)
        report.append({"pass": "rubric:%s" % rubric, "tiles": stats,
                       "unique_so_far": len(found)})
        print("rubric %-7s unique_so_far=%d tiles=%d requests=%d" % (
            rubric, len(found), len(stats), requests_made))
        time.sleep(SLEEP)

    # Pass 2: the two text queries, tile-collected because totals exceed 50.
    for query in QUERIES:
        stats: List[Dict[str, Any]] = []
        tile_collect({"q": query, "fields": FIELDS}, ROOT_BBOX, "query:%s" % query, 0, stats)
        report.append({"pass": "query:%s" % query, "tiles": stats,
                       "unique_so_far": len(found)})
        print("query tile pass done unique=%d tiles=%d requests=%d" % (
            len(found), len(stats), requests_made))

    # Pass 3: facet bookkeeping — rubric counts and city list for the whole country.
    facet = get(ITEMS, {
        "q": QUERIES[0], "polygon": "POLYGON((67.30 36.60, 75.20 36.60, 75.20 41.10, "
                                    "67.30 41.10, 67.30 36.60))",
        "page_size": PAGE_SIZE, "fields": "filters",
    })
    filters = ((facet.get("result") or {}).get("filters") or {})
    country = {
        "total": (facet.get("result") or {}).get("total"),
        "cities": (filters.get("spatial") or {}).get("cities") or [],
        "rubrics": filters.get("rubrics") or [],
    }

    ids = list(found.keys())
    contacts = probe_contacts(ids[:40])

    enriched: Dict[str, Dict[str, Any]] = {}
    for index in range(0, len(ids), 20):
        data = get(BYID, {"ids": ",".join(ids[index:index + 20]),
                          "fields": "items.reviews,items.rubrics,items.address_name,items.point,items.adm_div"})
        for item in (data.get("result") or {}).get("items") or []:
            enriched[str(item.get("id"))] = item
        time.sleep(SLEEP)

    rows: List[Dict[str, Any]] = []
    for item_id, item in found.items():
        full = enriched.get(item_id) or {}
        rubric_names = [r.get("name") for r in (full.get("rubrics") or item.get("rubrics") or [])]
        rubric_ids = [str(r.get("id")) for r in (full.get("rubrics") or item.get("rubrics") or [])]
        city_adm = next((a for a in (full.get("adm_div") or item.get("adm_div") or [])
                         if a.get("type") == "city"), {})
        district = next((a.get("name") for a in (full.get("adm_div") or item.get("adm_div") or [])
                         if a.get("type") == "district"), None)
        reviews = full.get("reviews") or item.get("reviews") or {}
        point = full.get("point") or item.get("point") or {}
        rows.append({
            "id": item_id,
            "name": full.get("name") or item.get("name"),
            "rating": rating_of(full) if rating_of(full) is not None else rating_of(item),
            "review_count": reviews.get("general_review_count") or reviews.get("org_review_count"),
            "address": full.get("address_name") or item.get("address_name"),
            "district": district,
            "city_alias": city_adm.get("city_alias") or CITY_ALIAS,
            "lon": point.get("lon"),
            "lat": point.get("lat"),
            "rubric_ids": rubric_ids,
            "rubric_names": rubric_names,
            "reviews_raw": reviews,
            "url_2gis": "https://2gis.tj/%s/firm/%s" % (CITY_ALIAS, item_id),
            "passes": item["_passes"],
        })

    rows.sort(key=lambda r: (-(r["rating"] or 0), r["name"] or ""))
    ge4 = [r for r in rows if (r["rating"] or 0) >= RATING_MIN]

    with io.open(os.path.join(HERE, "items_all.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    with io.open(os.path.join(HERE, "items_ge4.json"), "w", encoding="utf-8") as fh:
        json.dump(ge4, fh, ensure_ascii=False, indent=1)
    with io.open(os.path.join(HERE, "collect_report.json"), "w", encoding="utf-8") as fh:
        json.dump({"passes": report, "country_facet": country,
                   "contact_probe": contacts, "requests_made": requests_made,
                   "total_items": len(rows), "items_ge_4": len(ge4)},
                  fh, ensure_ascii=False, indent=1)

    print("items=%d rating>=4=%d requests=%d contact_probe=%s" % (
        len(rows), len(ge4), requests_made,
        json.dumps({k: v.get("contacts_present") for k, v in contacts.items()},
                   ensure_ascii=False)))


if __name__ == "__main__":
    main()
