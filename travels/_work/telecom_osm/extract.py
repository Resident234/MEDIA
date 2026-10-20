# -*- coding: utf-8 -*-
"""Из osm_raw.json (Overpass-выгрузка) → rows_osm.jsonl с полями:
name, operator, city_ru, addr, lat, lon, osm_url, source.

usage: python extract.py

Правила фильтрации (только то, что реально салон/офператор связи):
- shop == "mobile_phone" — включаем безусловно
- office == "telecommunication" — включаем (Tojiktelecom и т.п.)
- amenity == "telephone_office" — включаем
- иначе только если name содержит оператора (Tcell/Megafon/Zet/...)
- ИСКЛЮЧАЕМ если name/brand указывает на несвязевой магазин (country_store,
  supermarket), даже если содержит "Tcell" — это可能是 Тсел-кафе и т.п.

Город — ближайший из ~25 таджикистанских городов по great-circle. Если
расстояние > 60 км — пишем "?" или "Сельская местность".
"""
import io
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "osm_raw.json")
OUT = os.path.join(HERE, "rows_osm.jsonl")

CITIES = [
    (u"Душанбе", 38.5598, 68.7864),
    (u"Худжанд", 40.2823, 69.6182),
    (u"Истаравшан", 39.9177, 69.0078),
    (u"Канибадам", 40.3759, 70.4228),
    (u"Исфара", 40.1136, 70.6235),
    (u"Нафус/Зафарабад", 39.1444, 69.9764),
    (u"Пенджикент", 39.4902, 67.6083),
    (u"Айни (Закирт)", 39.4186, 68.5744),
    (u"Ашт", 39.7526, 70.6887),
    (u"Ош", 39.7513, 71.0093),  # Kyrgyz border but nearby
    (u"Ура-Тюбе", 40.0025, 69.7355),
    (u"Куйбышевский/Гиссар", 38.5164, 68.2198),
    (u"Турсунзаде", 38.5122, 68.2164),
    (u"Вахдат", 38.1252, 69.0431),
    (u"Рудаки", 38.7527, 68.5744),
    (u"Бохтар (Курган-Тюбе)", 37.8364, 68.7803),
    (u"Вахш", 37.7250, 68.8880),
    (u"Куляб", 37.9123, 69.7803),
    (u"Калай-Хумб (Ишкашим)", 36.8486, 71.4375),
    (u"Рошткала (Шугнан)", 37.4683, 71.5492),
    (u"Хорог (Бадахшан)", 37.4894, 71.5541),
    (u"Ишкашим", 36.7294, 71.4050),
    (u"Рушан", 37.8555, 71.9821),
    (u"Вахан (Сарг-Банда?)", 37.6111, 71.5500),
    (u"Мургаб", 38.1775, 73.9717),
    (u"Нурек", 38.3939, 69.2958),
    (u"Файзабад", 39.1925, 70.3907),
    (u"Рашид-Каром (Рашт)", 39.3125, 70.3517),
    (u"Джергарон (Файзобод)", 38.8620, 69.8980),
    (u"Сангвед/Соим", 39.0000, 70.0000),
    (u"Шамсиддин-Один (Окиму)", 39.0156, 70.8621),
    (u"Тавиль-Гара", 39.4000, 70.5000),
    (u"Дусти (Чирчик-Юж)", 38.2270, 68.7825),
    (u"Орзу", 39.3400, 69.4900),
    (u"Сарбор (Джабрасул)", 38.1400, 69.1700),
    (u"Кзыл-Рабат (Хатлон)", 37.4829, 68.8672),
    (u"Муминабад (Кубодиён)", 38.7125, 69.0483),
    (u"Джабрасул", 37.6400, 69.3200),
    (u"Пяндж (Сикпа)", 37.0411, 69.1900),
    (u"Ишкошим-Новый", 36.8497, 71.4388),
    (u"Восе", 37.5203, 70.5417),
    (u"Дарваз", 37.6067, 70.8347),
    (u"Оби-Хавоид (Калаифом)", 37.7700, 70.7100),
    (u"Рохартич/Вомар", 39.3000, 71.3000),
    (u"Пархар (Ляхш)", 39.0500, 70.6500),
    (u"Ванч", 39.4000, 71.6200),
]

OP_PATTERNS = [
    (u"Tcell", re.compile(r"\bTcell\b|Тсел", re.UNICODE)),
    (u"МегаФон", re.compile(r"Megafon|MegaFon|МегаФон|Мегафон", re.UNICODE)),
    (u"Зет-Мобайл (ex-Beeline)", re.compile(r"\bZet\b|Зет|Beeline", re.UNICODE)),
    (u"Бабилон", re.compile(r"Babilon|Бабилон", re.UNICODE)),
    (u"Тоҷиктелеком", re.compile(r"Tojiktelecom|Тоҷиктелеком|Таджиктелеком", re.UNICODE)),
    (u"Норак (MTT)", re.compile(r"Норак|Norak|MTT", re.UNICODE)),
    (u"ИндигО", re.compile(r"Indigo|ИндигО", re.UNICODE)),
    (u"Мобайл+", re.compile(r"\bOmobile\b|O mobile|Mobile\+|Мобайл", re.UNICODE | re.IGNORECASE)),
]

NON_TELECOM_HINT = re.compile(
    r"cafe|coffe|бар\b|ресторан|пиццерия|country_store|супермаркет|market\b",
    re.UNICODE | re.IGNORECASE)


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def nearest_city(lat, lon):
    best = (None, 1e9, 0)
    for name, clat, clon in CITIES:
        d = haversine(lat, lon, clat, clon)
        if d < best[1]:
            best = (name, d, best[2] + 1)
    if best[1] <= 30:
        return best[0], round(best[1], 1)
    if best[1] <= 80:
        return best[0] + u" (окр.)", round(best[1], 1)
    return u"", round(best[1], 1)


def detect_operator(text):
    for label, rx in OP_PATTERNS:
        if rx.search(text):
            return label
    return None


def is_telecom(tags, name):
    if NON_TELECOM_HINT.search(name or ""):
        return False
    shop = tags.get("shop")
    if shop == "mobile_phone":
        return True
    if tags.get("amenity") == "telephone_office":
        return True
    if tags.get("office") == "telecommunication":
        return True
    if detect_operator(name):
        return True
    return False


def main():
    d = json.load(io.open(SRC, encoding="utf-8"))
    els = d.get("elements", [])
    written = 0
    skipped = 0
    with io.open(OUT, "w", encoding="utf-8") as f:
        for e in els:
            tags = e.get("tags") or {}
            name = tags.get("name") or tags.get("name:ru") or tags.get("name:en") or ""
            if not name:
                skipped += 1
                continue
            if not is_telecom(tags, name):
                skipped += 1
                continue
            lat = e.get("lat") or (e.get("center") or {}).get("lat")
            lon = e.get("lon") or (e.get("center") or {}).get("lon")
            if lat is None or lon is None:
                skipped += 1
                continue
            city, dist = nearest_city(lat, lon)
            op = detect_operator(name) or detect_operator(tags.get("brand") or "") or u"Прочие салоны"
            addr_parts = []
            for k in ("addr:street", "addr:house_number", "addr:housenumber"):
                if tags.get(k):
                    addr_parts.append(tags[k])
            addr = u", ".join(addr_parts) or (tags.get("addr:full") or "")
            row = {
                "osm_type": e["type"],
                "osm_id": e["id"],
                "name": name,
                "operator": op,
                "city": city,
                "city_dist_km": dist,
                "addr_street": addr,
                "addr_city_tag": tags.get("addr:city") or "",
                "shop": tags.get("shop") or "",
                "office": tags.get("office") or "",
                "brand": tags.get("brand") or "",
                "phone": tags.get("phone") or "",
                "website": tags.get("website") or tags.get("url") or "",
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "osm_url": "https://www.openstreetmap.org/%s/%d" % (e["type"], e["id"]),
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
    print("wrote %d, skipped %d" % (written, skipped))
    # summary by city
    from collections import Counter
    rows = [json.loads(l) for l in io.open(OUT, encoding="utf-8")]
    cc = Counter(r["city"] for r in rows)
    oc = Counter(r["operator"] for r in rows)
    print("cities:", json.dumps(dict(cc.most_common(15)), ensure_ascii=True))
    print("operators:", json.dumps(dict(oc.most_common(10)), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
