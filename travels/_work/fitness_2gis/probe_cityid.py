#!/usr/bin/env python3
"""Find the real 2GIS catalog city ids for Tajik towns and test strict polygons.

coverage() proved that `city_id` works only for Dushanbe: every other adm_div id
geocoded from a city name answers 404 itemNotFound. The docs say catalog city
ids are obtained with /3.0/items?type=adm_div.city (by name or by lon/lat), and
that `location` only reorders results instead of restricting them, while
`polygon` restricts strictly. This probe compares three ways of confining a
search to a Tajik town:

  1. type=adm_div.city reverse geocode -> candidate city_id -> city_id search
  2. polygon search around the town
  3. point1/point2 bbox search around the town

Every answer records meta.code/total and how many of the first items are
actually in Tajikistan, so a wrong-city match cannot pass unnoticed.
Key comes from TWOGIS_API_KEY only.
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
TJ_WORDS = ("Таджикистан", "Тоҷикистон")
QUERIES = ["Фитнес", "Тренажерный зал"]
FIELDS = "items.reviews,items.address_name,items.point,items.adm_div,items.rubrics"

# Town centres taken from coverage.json (all inside the Tajikistan bounding box).
CENTERS = [
    ("Душанбе", 68.769311, 38.557039),
    ("Худжанд", 69.614910, 40.290743),
    ("Куляб", 69.795687, 37.908385),
    ("Бохтар", 68.780259, 37.835790),
    ("Истаравшан", 69.008671, 39.916858),
    ("Турсунзаде", 68.219934, 38.513490),
    ("Вахдат", 69.012891, 38.556198),
    ("Пенджикент", 67.606311, 39.493536),
    ("Исфара", 70.606142, 40.113321),
    ("Канибадам", 70.435268, 40.288466),
    ("Нурек", 69.298222, 38.391845),
    ("Мургаб", 73.974968, 38.178442),
    ("Хорог", 71.589004, 37.490551),
    ("Гиссар", 68.553657, 38.526938),
    ("Ванч", 71.456477, 38.372081),
    ("Лахш", 71.381897, 39.339819),
    ("Файзабад", 70.035000, 38.554000),
    ("Истиклол", 69.650520, 40.585009),
    ("Шамсидин Шуҳин", 70.049143, 37.725966),
    ("Яван", 70.816000, 39.335000),
    ("Кумсангир", 68.383000, 37.567000),
    ("Рошан", 71.739000, 37.308000),
    ("Джиргатол", 69.992000, 39.092000),
]


def get(params: Dict[str, Any]) -> Dict[str, Any]:
    for attempt in range(4):
        try:
            response = requests.get(ITEMS, params={**params, "key": KEY}, timeout=60)
            data = response.json()
        except (requests.RequestException, ValueError):
            time.sleep(2 + 3 * attempt)
            continue
        code = (data.get("meta") or {}).get("code")
        if code in (429, 408):
            time.sleep(15 + 15 * attempt)
            continue
        return data
    return {"meta": {"code": 0, "error": {"type": "network_failed"}}}


def country_of(item: Dict[str, Any]) -> Optional[str]:
    for adm in item.get("adm_div") or []:
        if adm.get("type") == "country":
            return adm.get("name")
    return None


def is_tajik(item: Dict[str, Any]) -> bool:
    name = country_of(item) or ""
    return any(w in name for w in TJ_WORDS)


def polygon(lon: float, lat: float, half: float) -> str:
    return "POLYGON((%.6f %.6f, %.6f %.6f, %.6f %.6f, %.6f %.6f, %.6f %.6f))" % (
        lon - half, lat - half, lon + half, lat - half,
        lon + half, lat + half, lon - half, lat + half,
        lon - half, lat - half,
    )


def summarize(data: Dict[str, Any]) -> Dict[str, Any]:
    meta = data.get("meta") or {}
    result = data.get("result") or {}
    items = result.get("items") or []
    return {
        "code": meta.get("code"),
        "error": (meta.get("error") or {}).get("type"),
        "total": result.get("total"),
        "n": len(items),
        "tajik": sum(1 for i in items if is_tajik(i)),
        "countries": sorted({country_of(i) or "-" for i in items}),
        "first": [
            {
                "id": i.get("id"),
                "name": i.get("name"),
                "type": i.get("type"),
                "full_name": i.get("full_name"),
                "rating": (i.get("reviews") or {}).get("general_rating"),
            }
            for i in items[:5]
        ],
    }


def main() -> None:
    rows: List[Dict[str, Any]] = []
    for name, lon, lat in CENTERS:
        entry: Dict[str, Any] = {"city": name, "lon": lon, "lat": lat}

        city = get({"lon": "%.6f" % lon, "lat": "%.6f" % lat, "type": "adm_div.city"})
        entry["adm_div_city"] = summarize(city)

        adm = get({"lon": "%.6f" % lon, "lat": "%.6f" % lat})
        entry["reverse"] = summarize(adm)

        city_ids = [str(i["id"]) for i in (city.get("result") or {}).get("items") or [] if i.get("id")]
        entry["city_ids"] = city_ids

        for query in QUERIES:
            if city_ids:
                entry["city_id|%s" % query] = summarize(get({
                    "q": query, "city_id": ",".join(city_ids[:5]),
                    "page_size": 10, "fields": FIELDS,
                }))
            entry["polygon|%s" % query] = summarize(get({
                "q": query, "polygon": polygon(lon, lat, 0.05),
                "page_size": 10, "fields": FIELDS,
            }))
            entry["bbox|%s" % query] = summarize(get({
                "q": query,
                "point1": "%.6f,%.6f" % (lon - 0.01, lat + 0.01),
                "point2": "%.6f,%.6f" % (lon + 0.01, lat - 0.01),
                "page_size": 10, "fields": FIELDS,
            }))
            time.sleep(0.3)

        poly = entry.get("polygon|Фитнес", {})
        print("city %-18s cityids=%s adm=%s poly_total=%s poly_tajik=%s bbox_total=%s bbox_tajik=%s" % (
            name.encode("ascii", "backslashreplace").decode("ascii"),
            city_ids, entry["adm_div_city"]["code"], poly.get("total"),
            poly.get("tajik"), entry.get("bbox|Фитнес", {}).get("total"),
            entry.get("bbox|Фитнес", {}).get("tajik"),
        ))
        rows.append(entry)

    with io.open(os.path.join(HERE, "probe_cityid.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    print("wrote probe_cityid.json rows=%d" % len(rows))


if __name__ == "__main__":
    main()
