#!/usr/bin/env python3
"""Collect Osh short-stay apartments, hotels and guest houses via 2GIS Places API.

The API key is read only from TWOGIS_API_KEY. It is never written to output files.
"""
from __future__ import annotations

import argparse
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

API = "https://catalog.api.2gis.com/3.0/items"
BASE = "https://2gis.kg"
CENTER_LON, CENTER_LAT = 72.79196, 40.524099
# Four overlapping tiles avoid the Places API's five-page pagination ceiling.
TILES = [(CENTER_LON + dx, CENTER_LAT + dy) for dx, dy in (
    (-0.035, -0.025), (-0.035, 0.025), (0.035, -0.025), (0.035, 0.025)
)]
RADIUS = 7000
PAGE_SIZE = 10
MAX_PAGES = 5
FIELDS = "items.reviews,items.contact_groups,items.adm_div,items.address_name,items.rubrics"
OUT = Path(__file__).with_name("osh_2gis_api_whatsapp.md")

SOURCES = (
    ("Квартиры посуточно", 19487, "apartments"),
    ("Гостиницы", 269, "hotels"),
    ("Гостевые дома", 111005, "guesthouses"),
)


def api_get(key: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(API, params={**params, "key": key}, timeout=45)
    response.raise_for_status()
    data = response.json()
    meta = data.get("meta", {})
    if meta.get("code") != 200:
        raise RuntimeError(f"2GIS API error {meta.get('code')}: {meta.get('error', {}).get('message')}")
    return data


def is_osh(item: dict[str, Any]) -> bool:
    return any(
        adm.get("type") == "city" and adm.get("city_alias") == "osh"
        for adm in item.get("adm_div", [])
    )


def whatsapp(item: dict[str, Any]) -> str | None:
    for group in item.get("contact_groups", []):
        for contact in group.get("contacts", []):
            if contact.get("type") == "whatsapp":
                return contact.get("url") or contact.get("value")
    return None


def whatsapp_from_card(item: dict[str, Any]) -> str | None:
    """Read the public 2GIS card only when API contact_groups is unavailable."""
    response = requests.get(card_url(item), headers={"User-Agent": "Mozilla/5.0"}, timeout=45)
    response.raise_for_status()
    html = response.text
    # Prefer the compact wa.me URL; cards can also contain a wrapped
    # api.whatsapp.com URL with an internal 2GIS redirect.
    match = re.search(r"https?://wa\.me/[0-9]+(?:\?[^\"'<>\\s]+)?", html)
    if match:
        return match.group(0).replace("&amp;", "&")
    match = re.search(r"https?://api\.whatsapp\.com/send/[^\"'<>\\s]+", html)
    return match.group(0).replace("&amp;", "&") if match else None


def collect_source(key: str, title: str, rubric_id: int) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for lon, lat in TILES:
        for page in range(1, MAX_PAGES + 1):
            data = api_get(key, {
                "q": title,
                "rubric_id": rubric_id,
                "location": f"{lon:.6f},{lat:.6f}",
                "radius": RADIUS,
                "page": page,
                "page_size": PAGE_SIZE,
                "fields": FIELDS,
                "locale": "ru_KG",
            })
            rows = data.get("result", {}).get("items", [])
            for item in rows:
                if item.get("id") and is_osh(item):
                    found[str(item["id"])] = item
            if len(rows) < PAGE_SIZE:
                break
            time.sleep(0.25)
    return list(found.values())


def card_url(item: dict[str, Any]) -> str:
    return f"{BASE}/osh/firm/{item['id']}"


def md(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    key = os.environ.get("TWOGIS_API_KEY")
    if not key:
        raise SystemExit("Set TWOGIS_API_KEY in the environment")

    sections: list[tuple[str, list[dict[str, Any]]]] = []
    contact_field_seen = False
    for title, rubric_id, _ in SOURCES:
        items = collect_source(key, title, rubric_id)
        selected = []
        for item in items:
            contact_field_seen |= "contact_groups" in item
            rating = float(item.get("reviews", {}).get("general_rating") or 0)
            wa = whatsapp(item)
            if rating >= 4.0 and not wa:
                wa = whatsapp_from_card(item)
                time.sleep(0.2)
            if rating >= 4.0 and wa:
                item["_wa"] = wa
                selected.append(item)
        selected.sort(key=lambda x: (-float(x["reviews"]["general_rating"]), x.get("name", "").lower()))
        sections.append((title, selected))
        print(f"{title}: найдено в Оше {len(items)}, рейтинг 4+ и WhatsApp {len(selected)}")

    if not contact_field_seen:
        print("WARNING: API key returned no contact_groups; request contact permission from 2GIS.")

    with args.output.open("w", encoding="utf-8", newline="\n") as out:
        out.write("# Организации Оша из 2GIS Places API\n\n")
        out.write("Фильтры: рейтинг **4.0 и выше**, наличие **WhatsApp**. Источник — 2GIS Places API 3.0.\n\n")
        total = sum(len(rows) for _, rows in sections)
        out.write(f"Всего отобрано: **{total}**.\n\n")
        for title, rows in sections:
            out.write(f"## {title}\n\n")
            if not rows:
                out.write("Подходящих записей не найдено.\n\n")
                continue
            for item in rows:
                rating = float(item["reviews"]["general_rating"])
                rating_text = str(int(rating)) if rating.is_integer() else f"{rating:.1f}"
                url = card_url(item)
                out.write(f"### {md(item.get('name', 'Без названия'))}\n\n")
                out.write(f"**Рейтинг:** {rating_text}\n\n")
                out.write(f"**Адрес:** {md(item.get('address_name') or 'адрес не указан')}\n\n")
                out.write(f"**Карточка 2GIS:** [{url}]({url})\n\n")
                out.write(f"**WhatsApp:** [WhatsApp]({item['_wa']})\n\n")


if __name__ == "__main__":
    main()
