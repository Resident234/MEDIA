# -*- coding: utf-8 -*-
"""Карточки 2ГИС для сервисов пересылки из части 8d (посылки/доставка).

Канал — catalog.api.2gis.com/3.0/items c city_id: демо-ключ его отдаёт, в
отличие от /items/search (400) и от geocode (только адм. деления). Ключ
читается из аргумента или окружения, на диск не пишется.

Результат: _parcel_2gis.jsonl (по строке на организацию) и человекочитаемый
_parcel_2gis.txt. Console не печатает кириллицу — только ASCII-статусы.
"""
import io
import json
import os
import sys
import time
from urllib.parse import quote

import requests

KEY = os.environ.get("TWOGIS_API_KEY") or (
    sys.argv[1] if len(sys.argv) > 1 else "")
if not KEY:
    sys.exit("pass key or set TWOGIS_API_KEY")

ITEMS = "https://catalog.api.2gis.com/3.0/items"
GEOCODE = "https://catalog.api.2gis.com/3.0/items/geocode"
HERE = os.path.dirname(os.path.abspath(__file__))
FIELDS = "items.point,items.address_name,items.name,items.full_name,items.rubrics,items.adm_div,items.phones"

# город -> (geoquery, alias для карточки)
CITIES = [
    (u"Душанбе", "dushanbe"),
    (u"Худжанд", "khujand"),
    (u"Куляб", "kulob"),
    (u"Бохтар", "bokhtar"),
]

# Тоҷик/рус рубрикаҳои бахши интиқол ва почта — барои онҳое, ки брендом
# муайян карда намешаванд (карго ва ғ.).
DELIVERY_RUBRICS = (
    u"почта", u"экспресс-почта", u"intiquoli", u"интиқоли байналмилалӣ",
    u"боркашонӣ", u"грузоперевозк", u"доставка грузов", u"логистик",
    u"нуқтаҳои додани фармоиш", u"пункты выдачи", u"kurerisk", u"курьерск",
)

# сервис из части 8d -> (брендовые токены, разрешать ли рубрику доставки, запросы)
QUERIES = [
    ("СДЭК", ([u"сдэк", u"cdek"], False, [u"СДЭК", u"CDEK"])),
    ("Boxberry", ([u"boxberry", u"боксберри"], False, [u"Boxberry", u"Боксберри"])),
    ("Wildberries ПВЗ", ([u"wildberries", u"вайлдберри", u"wb"], False,
                        [u"Wildberries", u"Вайлдберриз"])),
    ("Озон ПВЗ", ([u"ozon", u"озон"], False, [u"Ozon ПВЗ", u"Озон ПВЗ", u"Озон"])),
    ("Аист Экспресс", ([u"аист"], False, [u"Аист экспресс", u"Aist"])),
    ("Почтаи Аср", ([u"аср", u"asr"], False, [u"Аср почта", u"Почтаи Аср"])),
    ("Почтаи Тоҷик / Tajikpost", ([u"почтаи тоҷик", u"почтаи точик",
                                   u"tajikpost", u"тоҷикистон"], True,
                                  [u"Почтаи точик", u"Tajikpost", u"почта"])),
    ("DHL", ([u"dhl"], False, [u"DHL"])),
    ("BorEx", ([u"borex", u"борэкспресс"], False, [u"BorEx", u"Borex"])),
    ("Азия Экспресс", ([u"азия экспресс", u"asia express"], False,
                       [u"Азия экспресс", u"Asia express"])),
    ("ПЭК", ([u"пэк"], False, [u"ПЭК"])),
    ("EMS", ([u"ems"], False, [u"EMS почта", u"EMS"])),
    ("Карго / грузоперевозки", ([u"карго", u"cargo", u"tezbor", u"фармойш"],
                                True, [u"карго", u"грузоперевозки"])),
]


def get(url, params):
    for attempt in range(4):
        try:
            r = requests.get(url, params={**params, "key": KEY}, timeout=60)
            j = r.json()
            code = (j.get("meta") or {}).get("code")
            if code in (429, 408) or r.status_code == 429:
                time.sleep(8 + 8 * attempt)
                continue
            return j
        except Exception:
            time.sleep(2 + 3 * attempt)
    return {"meta": {"code": 0}, "result": {"items": []}}


def city_id(name):
    j = get(GEOCODE, {"q": name, "fields": "items.adm_div,items.point",
                      "locale": "ru_RU"})
    for it in (j.get("result") or {}).get("items") or []:
        if it.get("type") != "adm_div":
            continue
        chain = u" ".join([a.get("name") or u"" for a in (it.get("adm_div") or [])])
        # страновая цепочка в ответе не всегда приходит — полагаемся на то,
        # что ключ тайский (2gis.tj) и full_name/подтип — город
        if it.get("subtype") == "city" and (u"тоҷик" in chain.lower()
                or u"таджик" in chain.lower()
                or it.get("id")):
            return str(it.get("id"))
    return None


def rubric_texts(item):
    """Все тексты рубрик (имя + алиасы на всех локалях) в нижнем регистре."""
    out = []
    for r in item.get("rubrics") or []:
        if r.get("name"):
            out.append(r["name"].lower())
        for a in (r.get("aliases") or []):
            if a.get("name"):
                out.append(a["name"].lower())
    return out


def matches(item, tokens, allow_rubric):
    """Отсеивает шум: 2GIS расширяет незакрытые запросы до рубрик."""
    name = (item.get("name") or u"") + u" " + (item.get("full_name") or u"")
    name = name.lower()
    if any(t.lower() in name for t in tokens):
        return True
    if allow_rubric:
        rb = rubric_texts(item)
        if any(w in r for r in rb for w in DELIVERY_RUBRICS):
            return True
    return False


def main():
    fh = io.open(os.path.join(HERE, "_parcel_2gis.jsonl"), "w",
                 encoding="utf-8", newline="\n")
    txt = io.open(os.path.join(HERE, "_parcel_2gis.txt"), "w", encoding="utf-8")
    seen_ids = set()
    for cname, alias in CITIES:
        cid = city_id(cname)
        txt.write(u"\n================ %s (city_id=%s)\n" % (cname, cid))
        print("city %s id=%s" % (alias, cid))
        if not cid:
            continue
        for label, (tokens, allow_rubric, qs) in QUERIES:
            hit = None
            for q in qs:
                j = get(ITEMS, {"q": q, "city_id": cid, "page_size": 10,
                               "fields": FIELDS})
                items = (j.get("result") or {}).get("items") or []
                items = [x for x in items if x.get("id") and x.get("point")]
                items = [x for x in items if matches(x, tokens, allow_rubric)]
                if items:
                    hit = (q, items, (j.get("result") or {}).get("total"))
                    break
                time.sleep(0.4)
            if not hit:
                txt.write(u"  -- %-26s : нет карточки\n" % label)
                continue
            q, items, total = hit
            txt.write(u"  %-26s [%s] total=%s\n" % (label, q, total))
            for x in items[:4]:
                iid = str(x.get("id"))
                pt = x.get("point") or {}
                rec = {"label": label, "city": cname, "alias": alias,
                       "id": iid, "query": q,
                       "name": x.get("name") or x.get("full_name"),
                       "address": x.get("address_name"),
                       "lat": pt.get("lat"), "lon": pt.get("lon"),
                       "rubrics": rubric_texts(x)[:2],
                       "phones": [p.get("number") for p in (x.get("phones") or [])],
                       "url": "https://2gis.tj/%s/firm/%s/" % (alias, iid)}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if iid not in seen_ids:
                    seen_ids.add(iid)
                txt.write(u"     * %s | %s | %s,%s | %s | %s\n" % (
                    rec["name"], rec["address"], rec["lat"], rec["lon"],
                    u"/".join(rec["rubrics"]), rec["url"]))
            time.sleep(0.5)
    fh.close()
    txt.close()
    print("done unique ids=%d" % len(seen_ids))


if __name__ == "__main__":
    main()
