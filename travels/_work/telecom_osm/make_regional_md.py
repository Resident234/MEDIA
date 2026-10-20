# -*- coding: utf-8 -*-
"""Из telecom_osm/rows_osm.jsonl → regional_block.md (розділ «Регионы»).

usage: python make_regional_md.py

Исключаем Душанбе (уже покрыт 245 карточками 2ГИС). Остальное группируем
по городу (по убыванию размера), затем по оператору. Формат строки идентичен
душабинскому блоку: имя · lat, lon · [OSM](url) · [2ГИС](url) · _(адрес)_.
Для регионов 2ГИС-карточки нет, ставим ссылку на Yandex Maps search как
второй вариант (не карточка, а поисковая выдача — лучше, чем ничего).
"""
import io
import json
import os
import urllib.parse
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "rows_osm.jsonl")
OUT = os.path.join(HERE, "regional_block.md")

OP_PREF = [u"Tcell", u"МегаФон", u"Зет-Мобайл (ex-Beeline)", u"Бабилон",
           u"Тоҷиктелеком", u"Норак (MTT)", u"ИндигО", u"Мобайл+",
           u"Прочие салоны"]


def yx_search_url(name, city):
    q = u"%s %s" % (name, city)
    return u"https://yandex.com/maps/?text=" + urllib.parse.quote(q.encode("utf-8"))


def main():
    rows = [json.loads(l) for l in io.open(SRC, encoding="utf-8")]
    # Исключаем Душанбе и Гиссар (оба покрыты 2ГИС-прохождением)
    regional = [r for r in rows if not (r["city"].startswith(u"Душанбе") or
                                        r["city"].startswith(u"Куйбышевский"))]
    by_city = defaultdict(list)
    for r in regional:
        city_key = r["city"] or u"Вне населённых пунктов"
        by_city[city_key].append(r)

    city_order = sorted(by_city.keys(), key=lambda c: (-len(by_city[c]), c))

    lines = []
    lines.append(u"### Салоны связи — регионы Таджикистана (OSM)")
    lines.append(u"")
    lines.append(u"_Источник: OpenStreetMap (Overpass API). 2ГИС в Таджикистане существует только для Душанбе (см. блок выше), Яндекс.Карты агрессивно троттлят автоматические запросы, поэтому для регионов используется OSM — там, где есть проверенные точки с координатами. Для каждого салона — название, координаты, ссылка на OSM-карточку и ссылка на Яндекс-поиск по названию (откроется живая карточка Яндекса, если она там есть)._" % ())
    lines.append(u"")
    total_written = 0
    for c in city_order:
        items = by_city[c]
        lines.append(u"**%s** — %d салонов" % (c, len(items)))
        lines.append(u"")
        # Group by operator
        by_op = defaultdict(list)
        for r in items:
            by_op[r["operator"]].append(r)
        ops_sorted = [o for o in OP_PREF if o in by_op] + \
                     [o for o in by_op if o not in OP_PREF]
        for op in ops_sorted:
            arr = sorted(by_op[op], key=lambda r: (r["name"] or "").lower())
            lines.append(u"_**%s** (%d)_" % (op, len(arr)))
            for r in arr:
                lat = r["lat"]; lon = r["lon"]
                parts = [u"- **%s**" % r["name"],
                         u"· %.6f, %.6f" % (lat, lon)]
                parts.append(u"· [OSM](%s)" % r["osm_url"])
                parts.append(u"· [Яндекс-поиск](%s)" % yx_search_url(r["name"], c.split(u" (")[0]))
                if r.get("addr_street"):
                    parts.append(u"· _(%s)_" % r["addr_street"])
                elif r.get("phone"):
                    parts.append(u"· _(тел. %s)_" % r["phone"])
                lines.append(u" ".join(parts))
                total_written += 1
            lines.append(u"")
        lines.append(u"")

    header = u"<!-- TELECOM_REG_BLOCK_BEGIN -->\n"
    footer = u"\n<!-- TELECOM_REG_BLOCK_END -->\n"
    body = header + u"\n".join(lines).rstrip() + u"\n" + footer
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(body)
    print("wrote %s: %d cities, %d items, %d bytes"
          % (os.path.basename(OUT), len(city_order), total_written, len(body)))


if __name__ == "__main__":
    main()
