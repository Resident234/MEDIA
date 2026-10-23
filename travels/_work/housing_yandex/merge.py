# -*- coding: utf-8 -*-
"""Слить lists/*.jsonl в housing_yx.jsonl: дедуп, фильтр категорий, регион.

usage: python merge.py

Записи в списках уже содержат телефоны, соцсети, сайты и рейтинг (см.
yx_state.js), поэтому обход карточек не нужен. Дубли склеиваются по id:
телефоны/соцсети/сайты объединяются, рейтинг берётся из более полной записи.

Фильтр: оставляем только жильё (гостиницы, гостевые дома, хостелы,
квартиры посуточно, мотели) и только объекты в Таджикистане. Каждому
объекту приписывается ближайший населённый пункт из cities.py — так
объекты, найденные запросом соседнего города, попадают в свой город.
"""
import glob
import io
import json
import math
import os
import re

from cities import CITIES
from yxd import HOST

HERE = os.path.dirname(os.path.abspath(__file__))
LISTS = os.path.join(HERE, "lists")
OUT = os.path.join(HERE, "housing_yx.jsonl")

# Жильё: русские и таджикские названия категорий плюс классы Яндекса.
OK_RE = re.compile(
    u"гостиниц|отел|гостев|guest|хостел|hostel|квартир|апартамент|apartment|"
    u"мотел|motel|меҳмонхона|мехмонхона|меҳмонхона|постоял|мини-отел|"
    u"гостевой дом|усадба|коттедж|дача|турбаза|кемпинг|camping|глэмпинг|"
    u"hotel|guesthouse|guest_house|apart|resort", re.I)
# Явно не жильё, даже если рядом стоит слово «квартира» в названии.
NO_RE = re.compile(
    u"агентств|риэлтор|недвижимост|турагент|тураген|экскурс|банк|"
    u"баня|сауна|кафе|ресторан|магазин|аптека|парикмахер|"
    u"ремонт квартир|аренда без посредников", re.I)
LODGING_CLASSES = {"hotels", "hotel", "hostel", "apartments", "apartment",
                   "guest_house", "guesthouse", "motel", "camping", "resort"}
# Объявления о продаже жилья Яндекс кладёт в «Квартиры» вместе с отелями:
# жилые комплексы и новостройки — не средства размещения, даже если класс
# категории совпадает с апартаментами.
RESIDENTIAL_RE = re.compile(u"жилой комплекс|новостройк|риэлтор|застройщик|"
                            u"агентство недвижимост", re.I)
# Название страны приходит в трёх начертаниях, у одиночных карточек — пустое.
TJ_COUNTRIES = {u"Таджикистан", u"Тоҷикистон", u"Точикистон",
                u"Tajikistan", u"Tadjikistan"}


def uniq(seq):
    out, seen = [], set()
    for x in seq:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def cats_of(it):
    out = []
    for c in it.get("categories") or []:
        if isinstance(c, dict):
            out.append((c.get("name") or "", c.get("class") or "",
                        c.get("seoname") or ""))
        elif isinstance(c, str):
            out.append((c, "", ""))
    return out


def is_lodging(it):
    cats = cats_of(it)
    text = u" ".join(u" ".join(c) for c in cats)
    if RESIDENTIAL_RE.search(text):
        return False
    if any(c[1].lower() in LODGING_CLASSES for c in cats if c[1]):
        return True
    if OK_RE.search(text):
        return True
    # Категорий нет (одиночная карточка) — судим по названию.
    return bool(OK_RE.search(it.get("title") or "")) and not NO_RE.search(text)


def coords(it):
    c = it.get("coords")
    if isinstance(c, (list, tuple)) and len(c) >= 2:
        try:
            return float(c[0]), float(c[1])
        except (TypeError, ValueError):
            return None, None
    if isinstance(c, dict):
        try:
            return float(c.get("lon")), float(c.get("lat"))
        except (TypeError, ValueError):
            return None, None
    if isinstance(c, str) and "," in c:
        a, b = c.split(",", 1)
        try:
            return float(a), float(b)
        except ValueError:
            return None, None
    return None, None


def phones_of(it):
    out = []
    for p in it.get("phones") or []:
        if isinstance(p, dict):
            out.append((p.get("number") or p.get("value") or "").strip())
        elif isinstance(p, str):
            out.append(p.strip())
    return [p for p in uniq(out) if p]


def sites_of(it):
    out = []
    for u in it.get("urls") or []:
        if isinstance(u, dict):
            out.append((u.get("url") or u.get("href") or "").strip())
        elif isinstance(u, str):
            out.append(u.strip())
    return [u for u in uniq(out) if u.startswith("http")]


def socials_of(it):
    wa, tg, other = [], [], []
    for s in it.get("socialLinks") or []:
        if not isinstance(s, dict):
            continue
        href = (s.get("href") or "").strip()
        kind = (s.get("type") or "").lower()
        if not href:
            continue
        if "whatsapp" in kind or "wa.me" in href:
            wa.append(href)
        elif "telegram" in kind or "t.me" in href:
            tg.append(href)
        elif kind in ("viber", "skype", "email", "phone"):
            continue
        else:
            other.append(href)
    return uniq(wa), uniq(tg), uniq(other)


def rating_of(it):
    d = it.get("ratingData") or {}
    if not isinstance(d, dict):
        return None, 0
    val = d.get("ratingValue")
    try:
        val = round(float(val), 1) if val is not None else None
    except (TypeError, ValueError):
        val = None
    rev = d.get("reviewCount") or d.get("ratingCount") or 0
    try:
        rev = int(rev)
    except (TypeError, ValueError):
        rev = 0
    return val, rev


def card_url(it):
    iid = it.get("id")
    seo = it.get("seoname")
    if iid and seo:
        return "%s/maps/org/%s/%s/" % (HOST, seo, iid)
    if iid:
        return "%s/maps/org/%s/" % (HOST, iid)
    return it.get("href")


def km(lon1, lat1, lon2, lat2):
    dx = (lon1 - lon2) * math.cos(math.radians((lat1 + lat2) / 2)) * 111.32
    dy = (lat1 - lat2) * 110.57
    return math.hypot(dx, dy)


def nearest(lon, lat):
    best, dist = None, 1e9
    for name, hint, clon, clat, region in CITIES:
        d = km(lon, lat, clon, clat)
        if d < dist:
            best, dist = (name, clon, clat, region), d
    return best, dist


def main():
    orgs = {}
    for path in sorted(glob.glob(os.path.join(LISTS, "*.jsonl"))):
        src = os.path.basename(path).split("__")[0]
        for line in io.open(path, encoding="utf-8"):
            try:
                it = json.loads(line)
            except ValueError:
                continue
            key = it.get("id") or it.get("seoname") or it.get("title")
            if not key:
                continue
            rec = orgs.get(key)
            if rec is None:
                it["_from"] = [src]
                orgs[key] = it
                continue
            for f in ("phones", "urls", "socialLinks", "categories"):
                if not rec.get(f) and it.get(f):
                    rec[f] = it.get(f)
                elif rec.get(f) and it.get(f) and isinstance(rec[f], list) \
                        and isinstance(it[f], list):
                    seen = [json.dumps(x, sort_keys=True, ensure_ascii=False)
                            for x in rec[f]]
                    for x in it[f]:
                        k = json.dumps(x, sort_keys=True, ensure_ascii=False)
                        if k not in seen:
                            rec[f].append(x)
                            seen.append(k)
            if not rec.get("ratingData") and it.get("ratingData"):
                rec["ratingData"] = it.get("ratingData")
            if not rec.get("fullAddress") and it.get("fullAddress"):
                rec["fullAddress"] = it.get("fullAddress")
            if not rec.get("seoname") and it.get("seoname"):
                rec["seoname"] = it.get("seoname")
            for s in it.get("_from") or [src]:
                if s not in rec["_from"]:
                    rec["_from"].append(s)

    rows, dropped, foreign = [], 0, 0
    for it in orgs.values():
        country = (it.get("country") or "").strip()
        if country and country not in TJ_COUNTRIES:
            foreign += 1
            continue
        if not is_lodging(it):
            dropped += 1
            continue
        lon, lat = coords(it)
        town, dist = (None, None)
        if lon is not None:
            town, dist = nearest(lon, lat)
            if country == "" and dist is not None and dist > 40:
                foreign += 1
                continue
        rating, reviews = rating_of(it)
        wa, tg, socials = socials_of(it)
        rows.append({
            "id": it.get("id"),
            "name": (it.get("title") or "").strip(),
            "url": card_url(it),
            "address": (it.get("fullAddress") or it.get("address") or "").strip(),
            "city": town[0] if town else (it.get("_from") or [""])[0],
            "region": town[3] if town else u"прочее",
            "dist_km": round(dist, 1) if dist is not None else None,
            "lon": lon, "lat": lat,
            "rating": rating, "reviews": reviews,
            "phones": phones_of(it),
            "whatsapp": wa, "telegram": tg, "socials": socials,
            "sites": sites_of(it),
            "hours": it.get("workingTime"),
            "categories": [c[0] for c in cats_of(it) if c[0]],
            "found_in": it.get("_from"),
        })

    rows.sort(key=lambda r: (r["region"], r["city"],
                             -(r["rating"] or 0), -(r["reviews"] or 0),
                             r["name"]))
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    cov = {"phones": 0, "sites": 0, "socials": 0, "rating": 0}
    regions = {}
    for r in rows:
        if r["phones"]:
            cov["phones"] += 1
        if r["sites"]:
            cov["sites"] += 1
        if r["socials"] or r["whatsapp"] or r["telegram"]:
            cov["socials"] += 1
        if r["rating"]:
            cov["rating"] += 1
        regions[r["region"]] = regions.get(r["region"], 0) + 1
    print("rows=%d dropped_non_lodging=%d foreign=%d" % (
        len(rows), dropped, foreign))
    for f in ("phones", "sites", "socials", "rating"):
        print("  %s: %d" % (f, cov[f]))
    print("cities: %d" % len({r["city"] for r in rows}))
    for k in sorted(regions):
        print("  %s: %d" % (k.encode("ascii", "backslashreplace").decode("ascii"),
                            regions[k]))


if __name__ == "__main__":
    main()
