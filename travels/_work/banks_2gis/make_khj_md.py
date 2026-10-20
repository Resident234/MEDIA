# -*- coding: utf-8 -*-
"""Из banks_osm/osm_khj_banks.json → khujand_block.md.

usage: python make_khj_md.py

Худжант покрываем через OSM (2ГИС в Худжанде 404, Yandex троттлит).
Тэги whatsapp/telegram в OSM по банкам Худжанда практически не встречаются,
поэтому для них добавляем пустые слоты, но показываем phone если есть.
"""
import io
import json
import os
import re
import urllib.parse
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "banks_osm", "osm_khj_banks.json")
OUT = os.path.join(HERE, "khujand_block.md")

WA_MESSAGE = (u"Здравствуйте. Открываете ли вы карты нерезидентам "
              u"и на каких условиях ?")
WA_ENCODED = urllib.parse.quote(WA_MESSAGE.encode("utf-8"))


def normalize_name(t):
    nm = (t.get("name") or "").strip()
    if not nm:
        nm = (t.get("name:ru") or t.get("name:tg") or t.get("brand") or "").strip()
    return nm


def extract(el):
    tags = el.get("tags") or {}
    lat = el.get("lat")
    lon = el.get("lon")
    if lat is None and el.get("center"):
        lat = el["center"].get("lat")
        lon = el["center"].get("lon")
    if lat is None or lon is None:
        return None
    name = normalize_name(tags)
    if not name:
        return None
    addr_parts = []
    for k in ("addr:street", "addr:housenumber", "addr:city"):
        v = tags.get(k)
        if v:
            addr_parts.append(str(v))
    addr = ", ".join(addr_parts) if addr_parts else None
    phone = tags.get("phone") or tags.get("contact:phone")
    website = tags.get("website") or tags.get("contact:website")
    wa = tags.get("contact:whatsapp") or tags.get("whatsapp")
    tg = tags.get("contact:telegram") or tags.get("telegram")
    return {
        "id": "%s/%d" % (el["type"], el.get("id")),
        "osm_type": el["type"],
        "osm_id": el.get("id"),
        "osm_url": "https://www.openstreetmap.org/%s/%d" % (el["type"], el.get("id")),
        "name": name,
        "lat": lat,
        "lon": lon,
        "addr": addr,
        "phone": phone,
        "website": website,
        "whatsapp": wa,
        "telegram": tg,
        "tags": tags,
    }


def fmt_row(r):
    parts = [u"- **%s**" % r["name"],
             u"· %.6f, %.6f" % (r["lat"], r["lon"]),
             u"· [OSM](%s)" % r["osm_url"]]
    if r.get("phone"):
        parts.append(u"· _тел. %s_" % r["phone"])
    if r.get("website"):
        parts.append(u"· [Сайт](%s)" % r["website"])
    # WhatsApp / Telegram: OSM хранит либо wa.me URL, либо просто телефон.
    wa = r.get("whatsapp")
    if wa:
        if wa.isdigit() or (wa.startswith("+") and wa[1:].isdigit()):
            digits = re.sub(r"\D", "", wa)
            parts.append(u"· [WhatsApp](https://wa.me/%s?text=%s)" % (digits, WA_ENCODED))
        else:
            base = wa.split("?", 1)[0]
            parts.append(u"· [WhatsApp](%s?text=%s)" % (base, WA_ENCODED))
    tg = r.get("telegram")
    if tg:
        if tg.startswith("@"):
            parts.append(u"· [Telegram](https://t.me/%s)" % tg[1:])
        elif not tg.startswith("http"):
            parts.append(u"· [Telegram](https://t.me/%s)" % tg)
        else:
            parts.append(u"· [Telegram](%s)" % tg)
    if r.get("addr"):
        parts.append(u"· _(%s)_" % r["addr"])
    return u" ".join(parts)


def network_sort(row):
    hay = row["name"]
    # Сортировка по названию сети (алфавитно), внутри — по имени.
    return (hay.lower(),)


def main():
    d = json.load(io.open(SRC, encoding="utf-8"))
    els = d.get("elements", [])
    rows = []
    for e in els:
        r = extract(e)
        if r:
            rows.append(r)
    # Dedup по (name, lat, lon) — часто one node/way/rel дублирует другой.
    seen = set()
    uniq = []
    for r in rows:
        key = (r["name"].lower(), round(r["lat"], 4), round(r["lon"], 4))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    # Сортировка по имени.
    uniq.sort(key=lambda r: r["name"].lower())

    lines = []
    lines.append(u"### Банки — Худжанд")
    lines.append(u"")
    lines.append(
        u"_Источник: OpenStreetMap (Overpass API). 2ГИС в Таджикистане "
        u"индексирует только Душанбе (khujand/bokhtar/kulyab → HTTP 404), "
        u"Яндекс.Карты агрессивно троттлят автоматические запросы. OSM даёт "
        u"координаты и название отделения, но почти никогда — WhatsApp/Telegram. "
        u"Чтобы уточнить условия для нерезидента, используйте телефон из "
        u"карточки или найдите живую страницу банка в Яндексе по названию._"
    )
    lines.append(u"")
    written = 0
    for r in uniq:
        s = fmt_row(r)
        if s:
            lines.append(s)
            written += 1
    lines.append(u"")

    header = u"<!-- BANKS_KHJ_BLOCK_BEGIN -->\n"
    footer = u"\n<!-- BANKS_KHJ_BLOCK_END -->\n"
    body = header + u"\n".join(lines).rstrip() + u"\n" + footer
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(body)
    print("wrote %s: %d items (from %d raw), %d bytes"
          % (os.path.basename(OUT), written, len(els), len(body)))


if __name__ == "__main__":
    main()
