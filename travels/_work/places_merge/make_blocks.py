# -*- coding: utf-8 -*-
"""Собрать по одному markdown-блоку на каждый places__<slug>.md.

usage: python make_blocks.py

Вход: merged.jsonl. Выход: blocks/places__<slug>__map_block.md — готовые
тексты для вставки между маркерами `<!-- PLACES_MAP_BLOCK_BEGIN -->` и
`<!-- PLACES_MAP_BLOCK_END -->` в конец соответствующего sections/places__*.md.

Формат записи на объект:

  - **<Name>** — <lat>, <lon> · [2ГИС](<gis_url>) · [Яндекс](<yx_url>)

Если известна только одна из карточек — вторая отсутствует; если нет
координат — выводим только ссылку. Пустые/абстрактные объекты (не
нашлись нигде) просто не попадают в блок.
"""
import io
import json
import os
from collections import defaultdict, OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
MERGED = os.path.join(HERE, "merged.jsonl")
BLOCKS = os.path.join(HERE, "blocks")

# Порядок групп — тот же, что в самом файле; но мы его узнаём по первому
# появлению. Поэтому sorted=False.

HEADER = (u"\n<!-- PLACES_MAP_BLOCK_BEGIN -->\n"
          u"\n### Места на картах: координаты и ссылки\n\n"
          u"_Для каждого объекта из подраздела — координаты и карточка "
          u"2ГИС (где есть) и Яндекс.Карт (где есть). Абстрактные пункты "
          u"(«Стиль», «Общий облик», «Типовая застройка») и то, что не "
          u"нашлось ни на одной карте, в блок не попали._\n\n")
FOOTER = u"\n<!-- PLACES_MAP_BLOCK_END -->\n"


def parse_coords(s):
    if not s:
        return None
    try:
        a, b = s.split(",")
        return float(a), float(b)
    except (ValueError, AttributeError):
        return None


def fmt_coord(lat, lon):
    """Мы храним lon/lat по 2ГИС-модели; выводим «lat, lon» — как все карты."""
    return u"%.6f, %.6f" % (lat, lon)


def line_for(rec):
    name = rec["name"] or ""
    gis = rec.get("gis") or {}
    yx = rec.get("yx") or {}
    lat = lon = None
    if gis:
        try:
            lon = float(gis.get("lon")) if gis.get("lon") is not None else None
            lat = float(gis.get("lat")) if gis.get("lat") is not None else None
        except (TypeError, ValueError):
            lat = lon = None
    if (lat is None or lon is None) and yx.get("coords"):
        pc = parse_coords(yx.get("coords"))
        if pc:
            # Yandex data-coordinates = "lon,lat" (как в 2ГИС point)
            lon, lat = pc[0], pc[1]
    bits = [u"**%s**" % name]
    if lat is not None and lon is not None:
        bits.append(fmt_coord(lat, lon))
    links = []
    if gis.get("url_2gis"):
        links.append(u"[2ГИС](%s)" % gis["url_2gis"])
    yx_href = yx.get("href")
    if yx_href:
        if not yx_href.startswith("http"):
            yx_href = "https://yandex.kz" + yx_href
        links.append(u"[Яндекс](%s)" % yx_href)
    if links:
        bits.append(u" · ".join(links))
    addr = gis.get("address") or ""
    if addr:
        bits.append(u"_(%s)_" % addr)
    return u"- " + u" · ".join(bits)


def main():
    os.makedirs(BLOCKS, exist_ok=True)
    per_file = defaultdict(lambda: OrderedDict())
    for line in io.open(MERGED, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        gis = r.get("gis") or {}
        yx = r.get("yx") or {}
        # Пропускаем, если вообще ничего не найдено.
        if not gis and not yx:
            continue
        f = r["file"]
        grp = r.get("group") or ""
        per_file[f].setdefault(grp, []).append(r)
    total = 0
    for fname, groups in per_file.items():
        stem = os.path.splitext(fname)[0]
        out_path = os.path.join(BLOCKS, stem + u"__map_block.md")
        parts = [HEADER]
        cnt = 0
        for grp, items in groups.items():
            if grp:
                parts.append(u"**%s — на картах**\n\n" % grp)
            for it in items:
                parts.append(line_for(it) + u"\n")
                cnt += 1
            parts.append(u"\n")
        parts.append(FOOTER)
        io.open(out_path, "w", encoding="utf-8", newline="\n").write(
            u"".join(parts))
        total += cnt
        print(u"%s -> %d items" % (stem, cnt))
    print("TOTAL mapped objects: %d" % total)


if __name__ == "__main__":
    main()
