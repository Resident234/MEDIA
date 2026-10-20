# -*- coding: utf-8 -*-
"""Из telecom_2gis/rows.jsonl → section_5_block.md (душа: список салонов связи
Душанбе с координатами и ссылкой на карточку 2ГИС, сгрупирован по районам).

usage: python make_md.py

Фильтр: только is_telecom==true (рубрика «Мобильные операторы» или таджикский
эквивалент) — это 250 из 298 снятых. Остальные 48 — магазины аксессуаров,
платёжные терминалы и банки, попавшие через широкие запросы.

Оператор вычисляется по префиксу имени/org_name: Tcell / МегаФон / Zet-mobile
(ex-Beeline) / Бабилон / Тоҷиктелеком / прочее. Внутри района группировка по
оператору, затем по имени.
"""
import io
import json
import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = os.path.join(HERE, "rows.jsonl")
OUT = os.path.join(HERE, "section_5_block.md")

OP_PATTERNS = [
    ("Tcell", re.compile(r"\bTcell\b|\bТсел", re.IGNORECASE | re.UNICODE)),
    ("МегаФон", re.compile(r"МегаФон|Мегафон|MegaFon|Megafon", re.IGNORECASE | re.UNICODE)),
    ("Зет-Мобайл", re.compile(r"Zet-?mobile|\bЗет\b|\bBeeline\b", re.IGNORECASE | re.UNICODE)),
    ("Бабилон", re.compile(r"Babilon|\u0411\u0430\u0431\u0438\u043b\u043e\u043d", re.IGNORECASE | re.UNICODE)),
    ("Тоҷиктелеком", re.compile(r"Tojiktelecom|\u0422\u043e\u04b7\u0438\u043a\u0442\u0435\u043b\u0435\u043a\u043e\u043c|\u0422\u0430\u0434\u0436\u0438\u043a\u0442\u0435\u043b\u0435\u043a\u043e\u043c", re.IGNORECASE | re.UNICODE)),
]


def operator_of(row):
    hay = (row.get("name") or "") + " " + (row.get("org_name") or "")
    for label, rx in OP_PATTERNS:
        if rx.search(hay):
            return label
    return "Прочие салоны"


def district_bucket(d):
    if not d:
        return "Вне районов (пригород, трассы)"
    # "Сино район" → "Район Сино" — привычнее по-русски
    m = re.match(r"^(.+?)\s+район$", d)
    if m:
        return u"Район " + m.group(1)
    return d


def fmt_row(r):
    nm = (r.get("name") or "").strip()
    addr = (r.get("address_name") or "").strip()
    lat = r.get("lat")
    lon = r.get("lon")
    url = r.get("url_2gis") or ""
    if lat is None or lon is None:
        return None
    parts = [u"- **%s**" % nm,
             u"· %.6f, %.6f" % (lat, lon)]
    if url:
        parts.append(u"· [2ГИС](%s)" % url)
    if addr:
        parts.append(u"· _(%s)_" % addr)
    return u" ".join(parts)


def main():
    rows = [json.loads(l) for l in io.open(ROWS, encoding="utf-8") if l.strip()]
    tel = [r for r in rows if r.get("is_telecom")]
    by_dist = defaultdict(lambda: defaultdict(list))
    for r in tel:
        by_dist[district_bucket(r.get("district"))][operator_of(r)].append(r)

    # Stable district order — по убыванию размера
    dist_order = sorted(by_dist.keys(),
                        key=lambda d: (-sum(len(v) for v in by_dist[d].values()), d))
    op_pref = [u"Tcell", u"МегаФон", u"Зет-Мобайл", u"Бабилон", u"Тоҷиктелеком", u"Прочие салоны"]

    lines = []
    lines.append(u"### Салоны связи — Душанбе")
    lines.append(u"")
    lines.append(u"_По данным 2ГИС (рубрика «Мобильные операторы»): total=298, с telecom-руброй %d, со всеми координатами %d ниже. Для каждого салона — широта/долгота, ссылка на карточку и адрес. 2ГИС в Таджикистане индексирует только Душанбе; салоны в Худжанде, Бохтаре, Кулябе, Хороге и прочих городах — на Яндекс.Картах (см. блок «Регионы» ниже)._" % (len(tel), 0))
    lines.append(u"")

    total_written = 0
    for d in dist_order:
        bucket = by_dist[d]
        d_total = sum(len(v) for v in bucket.values())
        lines.append(u"**%s** — %d салонов" % (d, d_total))
        lines.append(u"")
        ordered_ops = [o for o in op_pref if o in bucket] + \
                      [o for o in bucket.keys() if o not in op_pref]
        for op in ordered_ops:
            items = sorted(bucket[op], key=lambda r: (r.get("name") or "").lower())
            lines.append(u"_**%s** (%d)_" % (op, len(items)))
            for r in items:
                s = fmt_row(r)
                if s:
                    lines.append(s)
                    total_written += 1
            lines.append(u"")
        lines.append(u"")

    header = u"<!-- TELECOM_BLOCK_BEGIN -->\n"
    footer = u"\n<!-- TELECOM_BLOCK_END -->\n"
    # Обновить преамбулу фактическим числом отрендеренных записей.
    body_lines = u"\n".join(lines).replace(u"%d ниже" % 0, u"%d ниже" % total_written)
    body = header + body_lines.rstrip() + u"\n" + footer
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(body)
    print("wrote %s: %d districts, %d items, %d bytes"
          % (os.path.basename(OUT), len(dist_order), total_written, len(body)))


if __name__ == "__main__":
    main()
