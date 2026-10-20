#!/usr/bin/env python3
"""Probe 2GIS coverage for Tajikistan: geocode cities, then count items per city.

Key comes only from TWOGIS_API_KEY. Output is written as UTF-8 files because the
Windows console cannot print Tajik/Cyrillic text.
"""
from __future__ import annotations

import io
import json
import os
import sys

import requests

KEY = os.environ.get("TWOGIS_API_KEY")
if not KEY:
    sys.exit("Set TWOGIS_API_KEY")
HERE = os.path.dirname(os.path.abspath(__file__))
GEOCODE = "https://catalog.api.2gis.com/3.0/items/geocode"
ITEMS = "https://catalog.api.2gis.com/3.0/items"

CITIES = [
    "Душанбе", "Худжанд", "Куляб", "Бохтар", "Курган-Тюбе", "Истаравшан",
    "Турсунзаде", "Вахдат", "Пенджикент", "Исфара", "Канибадам", "Нурек",
    "Рудаки", "Мургаб", "Хорог", "Восе", "Джиргатол", "Матча", "Адрасман",
    "Яван", "Файзабад", "Кумсангир", "Хаваст", "Гиссар", "Шахринав",
    "Сохибкор", "Орзу", "Спитамен", "Кайраккум", "Ишторба", "Рошан",
    "Ванч", "Калаи-Хумб", "Фархор", "Пяндж", "Сангвор", "Рашт", "Лахш",
]


def get(url, params):
    response = requests.get(url, params={**params, "key": KEY}, timeout=60)
    response.raise_for_status()
    return response.json()


def main():
    with io.open(os.path.join(HERE, "probe_geocode.txt"), "w", encoding="utf-8") as fh:
        for name in CITIES:
            try:
                data = get(GEOCODE, {"q": name, "locale": "ru_RU"})
            except Exception as exc:  # noqa: BLE001
                fh.write("%s ERR %s\n" % (name, repr(exc)[:100]))
                continue
            meta = data.get("meta", {})
            items = (data.get("result") or {}).get("items") or []
            fh.write("%s code=%s err=%s n=%s\n" % (
                name, meta.get("code"), (meta.get("error") or {}).get("type"), len(items)))
            for item in items[:4]:
                adm = item.get("adm_div") or []
                city = next((a for a in adm if a.get("type") == "city"), None)
                region = next((a for a in adm if a.get("type") == "region"), None)
                country = next((a for a in adm if a.get("type") == "country"), None)
                fh.write("   item type=%s id=%s name=%s | city_id=%s alias=%s | region_id=%s | country=%s\n" % (
                    item.get("type"), item.get("id"), item.get("name"),
                    (city or {}).get("id"), (city or {}).get("city_alias"),
                    (region or {}).get("id"), (country or {}).get("name")))
    print("geocode probe written")


if __name__ == "__main__":
    main()
