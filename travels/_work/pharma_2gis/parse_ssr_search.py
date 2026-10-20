# -*- coding: utf-8 -*-
"""Научиться вытаскивать карточки из серверного JSON страницы выдачи 2ГИС.

usage: python parse_ssr_search.py

Выдача `2gis.tj/<город>/search/<запрос>` отдаёт в HTML состояние страницы, где
уже лежат карточки первой страницы со всеми нужными разделу 11 полями: id,
название, адрес, координаты, рубрики (у «Аптек» id 207), `schedule` с
`working_hours`, `org_rating`, число отзывов. Если разбирается прямо из HTML,
часы работы и координаты достаются одним запросом на запрос, и отдельно
обвешивать каждую карточку не приходится.

Тренажёр на четырёх уже скачанных файлах: находит маркер `"items":[`, декодирует
массив через raw_decode и печатает, какие поля реально заполнены. ASCII-only в
консоль.
"""
import io
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def decode_items(body):
    """Первый валидный массив карточек после маркера "items":[ ."""
    pos = 0
    while True:
        i = body.find('"items":[', pos)
        if i < 0:
            return None, None
        start = i + len('"items":')
        try:
            arr, end = json.JSONDecoder().raw_decode(body, start)
        except ValueError:
            pos = start
            continue
        if isinstance(arr, list) and arr and isinstance(arr[0], dict) and \
                ("id" in arr[0] or "data" in arr[0]):
            return arr, body[:i]
        pos = start


def fields_of(item):
    d = item.get("data") if isinstance(item.get("data"), dict) else item
    out = {}
    out["id"] = d.get("id") or item.get("id")
    out["name"] = d.get("name")
    addr = d.get("address")
    if isinstance(addr, dict):
        out["address"] = addr.get("value") or addr.get("unified")
    elif addr:
        out["address"] = addr
    out["address_name"] = d.get("address_name")
    point = d.get("point") or (d.get("geometry") or {}).get("point") or item.get("point")
    if isinstance(point, dict):
        out["point"] = [point.get("lon"), point.get("lat")]
    elif isinstance(point, list):
        out["point"] = point
    elif point:
        out["point"] = str(point)[:60]
    rub = d.get("rubrics") or d.get("rubric_ids") or []
    out["rubrics"] = [r.get("id") for r in rub if isinstance(r, dict)] if rub and \
        isinstance(rub[0], dict) else rub
    sched = d.get("schedule")
    if isinstance(sched, dict):
        out["is_24x7"] = sched.get("is_24x7")
        wh = sched.get("Mon", {}).get("working_hours") if isinstance(sched.get("Mon"), dict) else None
        out["mon_hours"] = [(h.get("from"), h.get("to")) for h in wh or []]
        out["raw_keys"] = sorted(sched.keys())[:9]
    out["org_rating"] = d.get("org_rating")
    out["org_review_count"] = d.get("org_review_count")
    return out


def main():
    files = [f for f in sorted(os.listdir(HERE))
             if f.startswith("_probe_search_") and f.endswith(".html") and
             os.path.getsize(os.path.join(HERE, f)) > 1000]
    for f in files:
        body = io.open(os.path.join(HERE, f), encoding="utf-8").read()
        arr, _ = decode_items(body)
        tot = sorted(set(re.findall(r'"total"\s*:\s*(\d+)', body)))[:3]
        print(ascii_(f), "total=", tot, "items decoded=", len(arr) if arr else 0)
        if not arr:
            continue
        for it in arr[:2]:
            print("  keys:", ascii_(sorted(it.keys()))[:400])
            print("  fields:", ascii_(json.dumps(fields_of(it), ensure_ascii=True,
                                                 default=str))[:500])
        # сводка по заполненности полей на всем массиве
        filled = {}
        for it in arr:
            fo = fields_of(it)
            for k, v in fo.items():
                if v not in (None, [], "", {}):
                    filled[k] = filled.get(k, 0) + 1
        print("  filled:", ascii_(json.dumps(filled, ensure_ascii=True)),
              "of", len(arr))


if __name__ == "__main__":
    main()
