# -*- coding: utf-8 -*-
"""Слить rows.jsonl из places_2gis и places_yandex в один merged.jsonl.

usage: python merge_maps.py

Ключ слияния: (file, group, raw[:60]) — тот же, что в gis_resolve/yx_resolve.
Если обе стороны дали hit/org/list, держим обе карточки; если только одна —
вторую не выдумываем.

Выход: merged.jsonl, одна строка = объект с полями:
  file, group, raw, name, slug, city_ru, is_dus,
  gis: {kind, id, card_name, address, lon, lat, rating, url_2gis, ...} | None,
  yx:  {kind, href, name, coords, rating, text} | None.
"""
import io
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
GIS = os.path.join(HERE, "..", "places_2gis", "rows.jsonl")
YX = os.path.join(HERE, "..", "places_yandex", "rows.jsonl")
OUT = os.path.join(HERE, "merged.jsonl")


def norm(txt):
    if not txt:
        return ""
    txt = txt.lower()
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r"ё", "е", txt)
    txt = re.sub(r"[^a-z0-9\u0430-\u044f\s]", " ", txt)
    return " ".join(txt.split())


def tokens(txt):
    return set(t for t in norm(txt).split() if len(t) >= 3)


def plausible(want, got):
    wt, gt = tokens(want), tokens(got)
    if not wt or not gt:
        return False
    if len(wt) == 1:
        return norm(want) == norm(got)
    if wt <= gt or gt <= wt:
        return True
    inter = len(wt & gt)
    union = len(wt | gt)
    return bool(union and inter * 2 >= union)


def key(r):
    return (r.get("file"), r.get("group"), (r.get("raw") or "")[:60])


def read_ok(path, kinds, name_field="card_name"):
    if not os.path.exists(path):
        return {}
    out = {}
    for line in io.open(path, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("kind") not in kinds:
            continue
        # Для Яндекса поле имени называется `name`, для 2ГИС — `card_name`.
        got = r.get(name_field) or r.get("name") or ""
        want = r.get("name") or ""
        # 2ГИС уже прошёл revalidate; для Яндекса проверяем при слиянии.
        if name_field == "name" and not plausible(want, got):
            continue
        out[key(r)] = r
    return out


def main():
    gis = read_ok(GIS, ("hit",), name_field="card_name")
    yx = read_ok(YX, ("org", "list"), name_field="name")
    # Все ключи — из 2GIS rows (в них есть file/group/raw/name/slug/...)
    all_rows = {}
    if os.path.exists(GIS):
        for line in io.open(GIS, encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            all_rows[key(r)] = r
    if os.path.exists(YX):
        for line in io.open(YX, encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            all_rows.setdefault(key(r), r)
    fh = io.open(OUT, "w", encoding="utf-8", newline="\n")
    n_gis = n_yx = n_both = n_none = 0
    for k, base in all_rows.items():
        g = gis.get(k)
        y = yx.get(k)
        rec = {
            "file": base.get("file"),
            "group": base.get("group"),
            "raw": base.get("raw"),
            "name": base.get("name"),
            "slug": base.get("slug"),
            "city_ru": base.get("city_ru"),
            "is_dus": base.get("is_dus"),
            "gis": None, "yx": None,
        }
        if g:
            rec["gis"] = {kk: g.get(kk) for kk in (
                "kind", "id", "card_name", "address", "lon", "lat",
                "rating", "review_count", "url_2gis", "total")}
            n_gis += 1
        if y:
            rec["yx"] = {kk: y.get(kk) for kk in (
                "kind", "href", "name", "coords", "rating", "text")}
            n_yx += 1
        if g and y:
            n_both += 1
        if not g and not y:
            n_none += 1
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    fh.close()
    print("merged: total=%d gis=%d yx=%d both=%d none=%d -> %s" % (
        len(all_rows), n_gis, n_yx, n_both, n_none,
        os.path.basename(OUT)))


if __name__ == "__main__":
    main()
