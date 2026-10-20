#!/usr/bin/env python3
"""Enrich the collected items with full cards and recompute ratings.

Two fixes over collect_dushanbe.py:
  * /3.0/items/byid takes the parameter `id`, not `ids`; with `ids` the API
    answers code 400 incorrectParams and every field silently disappears.
  * a card can carry `reviews.org_rating` without `reviews.general_rating`
    (e.g. Pro Fit: org_rating 5, no general_rating), so the rating used for the
    >= 4.0 filter is general_rating falling back to org_rating.

The contact probe is repeated with the correct parameter so that the "no phones
in this key" conclusion is stated on evidence.
"""
from __future__ import annotations

import io
import json
import os
import time
from typing import Any, Dict, List, Optional

import requests

KEY = os.environ["TWOGIS_API_KEY"]
HERE = os.path.dirname(os.path.abspath(__file__))
BYID = "https://catalog.api.2gis.com/3.0/items/byid"
CITY_ALIAS = "dushanbe"
FIELDS = ("items.reviews,items.rubrics,items.adm_div,items.address_name,items.point,"
          "items.work_time,items.phones,items.contacts,items.contact_groups,items.urls")
RATING_MIN = 4.0


def byid(ids: List[str]) -> Dict[str, Any]:
    data = requests.get(BYID, params={"id": ",".join(ids), "fields": FIELDS, "key": KEY},
                        timeout=90).json()
    return data


def pick_rating(reviews: Dict[str, Any]) -> Optional[float]:
    for key in ("general_rating", "org_rating"):
        value = reviews.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def main() -> None:
    with io.open(os.path.join(HERE, "items_all.json"), encoding="utf-8") as fh:
        rows = json.load(fh)
    ids = [r["id"] for r in rows]

    cards: Dict[str, Dict[str, Any]] = {}
    probe: Dict[str, Any] = {}
    for index in range(0, len(ids), 50):
        batch = ids[index:index + 50]
        data = byid(batch)
        meta = data.get("meta") or {}
        items = (data.get("result") or {}).get("items") or []
        for item in items:
            cards[str(item.get("id"))] = item
        probe["batch_%d" % index] = {
            "code": meta.get("code"), "n": len(items),
            "keys": sorted({k for item in items for k in item.keys()}),
        }
        time.sleep(0.4)

    # One explicit contact probe on a single well-known card.
    single = byid(["70000001109657173"])
    sitem = ((single.get("result") or {}).get("items") or [{}])[0]
    probe["single_with_contacts"] = {
        "code": (single.get("meta") or {}).get("code"),
        "returned_keys": sorted(sitem.keys()),
        "phones": sitem.get("phones"),
        "contacts": sitem.get("contacts"),
        "contact_groups": sitem.get("contact_groups"),
        "urls": sitem.get("urls"),
    }

    out: List[Dict[str, Any]] = []
    for row in rows:
        card = cards.get(row["id"]) or {}
        reviews = card.get("reviews") or row.get("reviews_raw") or {}
        adm = card.get("adm_div") or []
        city_adm = next((a for a in adm if a.get("type") == "city"), {})
        district = next((a.get("name") for a in adm if a.get("type") == "district"), row.get("district"))
        rubrics = card.get("rubrics") or []
        point = card.get("point") or {}
        merged = dict(row)
        merged.update({
            "name": card.get("name") or row["name"],
            "address": card.get("address_name") or row.get("address"),
            "address_comment": card.get("address_comment"),
            "district": district,
            "city_alias": city_adm.get("city_alias") or CITY_ALIAS,
            "lon": point.get("lon") or row.get("lon"),
            "lat": point.get("lat") or row.get("lat"),
            "rubric_ids": [str(r.get("id")) for r in rubrics] or row.get("rubric_ids") or [],
            "rubric_names": [r.get("name") for r in rubrics] or row.get("rubric_names") or [],
            "rating": pick_rating(reviews),
            "rating_field": ("general_rating" if "general_rating" in reviews else
                             "org_rating" if "org_rating" in reviews else None),
            "general_rating": reviews.get("general_rating"),
            "org_rating": reviews.get("org_rating"),
            "review_count": reviews.get("general_review_count") or reviews.get("org_review_count")
                            or reviews.get("general_review_count_with_stars")
                            or reviews.get("org_review_count_with_stars"),
            "work_time": card.get("work_time"),
            "phones": card.get("phones"),
            "contacts": card.get("contacts"),
            "contact_groups": card.get("contact_groups"),
            "urls": card.get("urls"),
        })
        out.append(merged)

    out.sort(key=lambda r: (-(r["rating"] or 0), r["name"] or ""))
    ge4 = [r for r in out if (r["rating"] or 0) >= RATING_MIN]

    with io.open(os.path.join(HERE, "items_full.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    with io.open(os.path.join(HERE, "items_full_ge4.json"), "w", encoding="utf-8") as fh:
        json.dump(ge4, fh, ensure_ascii=False, indent=1)
    with io.open(os.path.join(HERE, "enrich_report.json"), "w", encoding="utf-8") as fh:
        json.dump({"probe": probe, "cards": len(cards), "items": len(out),
                   "ge4": len(ge4), "no_rating": sum(1 for r in out if r["rating"] is None),
                   "with_phones": sum(1 for r in out if r.get("phones"))},
                  fh, ensure_ascii=False, indent=1)

    print("cards=%d items=%d ge4=%d no_rating=%d with_phones=%d" % (
        len(cards), len(out), len(ge4),
        sum(1 for r in out if r["rating"] is None),
        sum(1 for r in out if r.get("phones"))))


if __name__ == "__main__":
    main()
