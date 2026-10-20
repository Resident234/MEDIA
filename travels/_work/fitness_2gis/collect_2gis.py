#!/usr/bin/env python3
"""Collect fitness / gym organisations of Tajikistan from 2GIS Places API 3.0.

Phase "coverage": resolve each city, verify the catalog really belongs to
Tajikistan, and record meta.total per query.
Phase "detail": paginate through city-scoped results and, where the visible
total exceeds the demo-key ceiling (5 pages x 10 items), add a coordinate-tile
pass; results are deduplicated by item id.

The API key is read only from TWOGIS_API_KEY and never written to disk.
Outputs are UTF-8 JSON files (the Windows console cannot print Tajik text).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

KEY = os.environ.get("TWOGIS_API_KEY")
if not KEY:
    sys.exit("Set TWOGIS_API_KEY in the environment")

HERE = os.path.dirname(os.path.abspath(__file__))
ITEMS = "https://catalog.api.2gis.com/3.0/items"
GEOCODE = "https://catalog.api.2gis.com/3.0/items/geocode"

QUERIES = ["Фитнес", "Тренажерный зал"]
TJ_WORDS = ("Таджикистан", "Тоҷикистон")

# Rubrics seen on the probed cards; used as a cross-check pass.
RUBRICS = {"267": "Тренажёрные залы", "268": "Фитнес-клубы", "51256": "Спортивные комплексы"}

CITIES = [
    "Душанбе", "Худжанд", "Куляб", "Бохтар", "Истаравшан", "Турсунзаде",
    "Вахдат", "Пенджикент", "Исфара", "Канибадам", "Нурек", "Мургаб",
    "Хорог", "Гиссар", "Ванч", "Рашт", "Лахш", "Файзабад", "Истиклол",
    "Конбулак", "Яван", "Кумсангир", "Джиргатол", "Рошан", "Шамсидин Шуҳин",
]

FIELDS = "items.reviews,items.address_name,items.point,items.adm_div,items.rubrics"
PAGE_SIZE = 10
MAX_PAGES = 5
SLEEP = 0.30


def get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    for attempt in range(4):
        try:
            response = requests.get(url, params={**params, "key": KEY}, timeout=60)
        except requests.RequestException as exc:
            print("net error retry=%d %s" % (attempt + 1, repr(exc)[:70]))
            time.sleep(2 + 3 * attempt)
            continue
        try:
            data = response.json()
        except ValueError:
            print("non-json http=%s retry=%d" % (response.status_code, attempt + 1))
            time.sleep(2 + 3 * attempt)
            continue
        code = (data.get("meta") or {}).get("code")
        if code in (429, 408) or response.status_code == 429:
            print("rate limited code=%s, sleeping" % code)
            time.sleep(20 + 20 * attempt)
            continue
        return data
    return {"meta": {"code": 0, "error": {"type": "network_failed"}}}


def in_tajikistan(item: Dict[str, Any]) -> bool:
    for adm in item.get("adm_div") or []:
        if adm.get("type") == "country" and any(w in (adm.get("name") or "") for w in TJ_WORDS):
            return True
    return False


def city_geocode(name: str) -> Optional[Dict[str, Any]]:
    """Resolve a city name to its adm_div id, keeping only Tajik matches.

    Returns {"city_id", "matched", "center"} or None. Geocoding is noisy:
    "Спитамен" answers with Spitak (Armenia), "Ишторба" with a building in
    Saint Petersburg, so the country chain of the candidate is checked here
    instead of being trusted from the name alone.
    """
    data = get(GEOCODE, {
        "q": name,
        "fields": "items.point,items.adm_div",
        "locale": "ru_RU",
    })
    fallback: Optional[Dict[str, Any]] = None
    for item in (data.get("result") or {}).get("items") or []:
        if item.get("type") != "adm_div":
            continue
        chain = item.get("adm_div") or []
        names = [a.get("name") for a in chain if a.get("name")]
        point = item.get("point") or {}
        center = None
        if point.get("lat") is not None and point.get("lon") is not None:
            center = (point["lon"], point["lat"])
        if center is None:
            bounds = (item.get("geometry") or {}).get("center") or {}
            if bounds.get("lat") is not None:
                center = (bounds["lon"], bounds["lat"])
        candidate = {
            "city_id": str(item.get("id")),
            "matched": item.get("name"),
            "chain": names,
            "chain_ok": any(any(w in n for w in TJ_WORDS) for n in names),
            "center": list(center) if center else None,
        }
        if candidate["chain_ok"]:
            return candidate
        if fallback is None:
            fallback = candidate
    # Geocoding sometimes omits the country chain; keep the candidate but let
    # the search pass below decide whether it really belongs to Tajikistan.
    return fallback


def search(params: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[int], Any, Any]:
    data = get(ITEMS, params)
    meta = data.get("meta") or {}
    result = data.get("result") or {}
    return (result.get("items") or [], result.get("total"),
            (meta.get("error") or {}).get("type"), meta.get("code"))


def paged_city_search(query: str, city_id: str) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    items: List[Dict[str, Any]] = []
    total: Optional[int] = None
    for page in range(1, MAX_PAGES + 1):
        got, tot, _, _ = search({
            "q": query, "city_id": city_id, "page": page,
            "page_size": PAGE_SIZE, "fields": FIELDS,
        })
        if total is None:
            total = tot
        items.extend(got)
        if len(got) < PAGE_SIZE:
            break
        time.sleep(SLEEP)
    return items, total


def tiles(center: Tuple[float, float]) -> List[Tuple[float, float]]:
    lon, lat = center
    pts = [(lon, lat)]
    for dlon in (-0.02, 0.0, 0.02):
        for dlat in (-0.02, 0.0, 0.02):
            if (lon + dlon, lat + dlat) != (lon, lat):
                pts.append((lon + dlon, lat + dlat))
    for dlon in (-0.045, 0.045):
        for dlat in (-0.045, 0.045):
            pts.append((lon + dlon, lat + dlat))
    return pts


def tile_search(query: str, center: Tuple[float, float], found: Dict[str, Dict[str, Any]], want: int) -> None:
    for lon, lat in tiles(center):
        if len(found) >= want:
            return
        for page in range(1, MAX_PAGES + 1):
            got, _, _, _ = search({
                "q": query, "location": "%.6f,%.6f" % (lon, lat), "radius": 4000,
                "page": page, "page_size": PAGE_SIZE, "fields": FIELDS,
            })
            for item in got:
                if item.get("id") and in_tajikistan(item):
                    found.setdefault(str(item["id"]), item)
            if len(got) < PAGE_SIZE:
                break
            time.sleep(SLEEP)
        time.sleep(SLEEP)


def coverage() -> None:
    rows = []
    for index, name in enumerate(CITIES):
        geo = city_geocode(name)
        entry: Dict[str, Any] = {
            "city": name,
            "city_id": geo["city_id"] if geo else None,
            "matched": geo["matched"] if geo else None,
            "chain": geo["chain"] if geo else [],
            "chain_ok": bool(geo and geo["chain_ok"]),
            "verified": False,
            "center": geo["center"] if geo else None,
            "totals": {},
            "codes": {},
        }
        if not geo:
            print("city#%02d no city id" % index)
            rows.append(entry)
            time.sleep(SLEEP)
            continue
        center = tuple(entry["center"]) if entry["center"] else None
        for query in QUERIES:
            for mode in ("city_id", "location"):
                params: Dict[str, Any] = {"q": query, "page_size": 3, "fields": FIELDS}
                if mode == "city_id":
                    params["city_id"] = entry["city_id"]
                elif center:
                    params["location"] = "%.6f,%.6f" % center
                    params["radius"] = 8000
                else:
                    continue
                items, total, err, code = search(params)
                entry["codes"]["%s|%s" % (query, mode)] = [code, err, total]
                tajik = [i for i in items if in_tajikistan(i)]
                if tajik:
                    entry["verified"] = True
                    if center is None:
                        point = tajik[0].get("point") or {}
                        if point.get("lat") is not None:
                            center = (point["lon"], point["lat"])
                            entry["center"] = [point["lon"], point["lat"]]
                    if mode == "city_id":
                        entry["totals"][query] = total
                time.sleep(SLEEP)
        print("city#%02d id=%s chain_ok=%s verified=%s center=%s totals=%s" % (
            index, entry["city_id"], entry["chain_ok"], entry["verified"],
            entry["center"], entry["totals"]))
        rows.append(entry)
    with io.open(os.path.join(HERE, "coverage.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    print("verified cities: %d of %d" % (
        sum(1 for r in rows if r["verified"]), len(rows)))


def detail() -> None:
    with io.open(os.path.join(HERE, "coverage.json"), encoding="utf-8") as fh:
        cov = json.load(fh)
    all_items: Dict[str, Dict[str, Any]] = {}
    report = []
    for entry in cov:
        if not entry.get("verified") or not entry.get("city_id"):
            continue
        if not any(entry.get("totals", {}).values()):
            continue
        center = tuple(entry["center"]) if entry.get("center") else None
        found: Dict[str, Dict[str, Any]] = {}
        want = 0
        for query in QUERIES:
            items, total = paged_city_search(query, entry["city_id"])
            want = max(want, total or 0)
            for item in items:
                if item.get("id") and in_tajikistan(item):
                    found.setdefault(str(item["id"]), item)
            time.sleep(SLEEP)
        if center and want > len(found):
            print("  %s: total %s > collected %s -> tile pass" % (entry["city"], want, len(found)))
            for query in QUERIES:
                tile_search(query, center, found, want)  # type: ignore[arg-type]
        for item_id, item in found.items():
            city_adm = next((a for a in item.get("adm_div") or [] if a.get("type") == "city"), {})
            record = dict(item)
            record["_city_alias"] = city_adm.get("city_alias")
            record["_city_name"] = city_adm.get("name")
            all_items[item_id] = record
        report.append({"city": entry["city"], "declared_total": want, "unique": len(found)})
        print("CITY %-18s declared=%s unique=%d" % (entry["city"], want, len(found)))
    with io.open(os.path.join(HERE, "items.json"), "w", encoding="utf-8") as fh:
        json.dump(list(all_items.values()), fh, ensure_ascii=False, indent=1)
    with io.open(os.path.join(HERE, "collect_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print("TOTAL unique items: %d" % len(all_items))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("coverage", "detail"))
    args = parser.parse_args()
    coverage() if args.phase == "coverage" else detail()


if __name__ == "__main__":
    main()
