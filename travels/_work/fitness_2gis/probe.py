#!/usr/bin/env python3
"""Probe what the 2GIS demo key actually returns for Tajikistan fitness items.

Key is read only from TWOGIS_API_KEY. Results are written as UTF-8 JSON/text files
because the Windows console cannot print Cyrillic/Tajik.
"""
from __future__ import annotations

import io
import json
import os
import sys

import requests

API = "https://catalog.api.2gis.com/3.0/items"
BYID = "https://catalog.api.2gis.com/3.0/items/byid"
OUT = os.path.dirname(os.path.abspath(__file__))
KEY = os.environ.get("TWOGIS_API_KEY")
if not KEY:
    sys.exit("Set TWOGIS_API_KEY")

CITIES = {
    "dushanbe": (68.786400, 38.559800),
    "khujand": (69.628200, 40.283100),
}
QUERIES = ["Фитнес", "Тренажерный зал"]
LOCALES = [None, "ru_RU", "ru_TJ"]

FIELDS = (
    "items.reviews,items.contact_groups,items.contacts,items.phones,items.address_name,"
    "items.point,items.adm_div,items.rubrics,items.external_urls,items.links,items.json"
)


def get(url, params):
    response = requests.get(url, params={**params, "key": KEY}, timeout=60)
    response.raise_for_status()
    return response.json()


def main():
    report = {}
    for alias, (lon, lat) in CITIES.items():
        per_query = {}
        for query in QUERIES:
            for locale in LOCALES:
                params = {
                    "q": query,
                    "location": "%.6f,%.6f" % (lon, lat),
                    "radius": 15000,
                    "page_size": 10,
                    "fields": FIELDS,
                }
                if locale:
                    params["locale"] = locale
                data = get(API, params)
                meta = data.get("meta", {})
                result = data.get("result") or {}
                items = result.get("items") or []
                per_query["%s|%s" % (query, locale or "-")] = {
                "code": meta.get("code"),
                "error": (meta.get("error") or {}).get("type"),
                "total": result.get("total"),
                "n": len(items),
                "sample": [
                    {
                        "id": i.get("id"),
                        "name": i.get("name"),
                        "address_name": i.get("address_name"),
                        "point": i.get("point"),
                        "adm_div": [
                            (a.get("type"), a.get("city_alias"), a.get("name"))
                            for a in (i.get("adm_div") or [])
                        ],
                        "reviews": i.get("reviews"),
                        "contact_groups": i.get("contact_groups"),
                        "contacts": i.get("contacts"),
                        "phones": i.get("phones"),
                        "rubrics": [(r.get("id"), r.get("title")) for r in (i.get("rubrics") or [])],
                    }
                    for i in items[:3]
                ],
            }
        report[alias] = per_query
    with io.open(os.path.join(OUT, "probe_search.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)

    # Full raw card of the first found item, to see every available field.
    first_id = None
    for alias, queries in report.items():
        for query, block in queries.items():
            for s in block["sample"]:
                if s["id"]:
                    first_id = s["id"]
                    break
            if first_id:
                break
        if first_id:
            break
    if first_id:
        raw = get(BYID, {"id": first_id, "fields": FIELDS, "locale": "ru_RU"})
        with io.open(os.path.join(OUT, "probe_card_full.json"), "w", encoding="utf-8") as fh:
            json.dump(raw, fh, ensure_ascii=False, indent=1)
    print("probe done: first_id=%s" % first_id)


if __name__ == "__main__":
    main()
