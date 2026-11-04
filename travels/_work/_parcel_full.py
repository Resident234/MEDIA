# -*- coding: utf-8 -*-
"""Полная выдача карточек пересылки/доставки по Душанбе через 2ГИС API.

В отличие от _parcel_2gis.py (там поиск по брендам из чата), этот скрипт
перечисляет ВСЕ организации по релевантным рубрикам каталога: канал
`catalog.api.2gis.com/3.0/items?rubric_id=<id>&city_id=<Dushanbe>` с
пагинацией. Демо-ключ отдаёт только Душанбе (остальные города — 404), поэтому
полная страна здесь = полная выдача столицы + внешние ссылки на остальные города
(см. примечание в конце).

Рубрики ядра темы (из _rub.txt):
  335     Почта
  338     Экспресс-почта
  9741    Интиқоли байналмилалии бор  (междун. грузоперевозки)
  417     Боркашонии автомобилии байнишаҳрӣ  (межгород. автогрузоперевозки)
  95584   Терминалҳои амонатӣ  (постаматы)
  112611  Нуқтаҳои додани фармоишҳои интернетӣ  (ПВЗ маркетплейсов)
Смежные (груз, но не посылки быта) — 423 ж/д, 402 авиа, 5279 склады, 844 таможня:
по умолчанию выключены, включите ADJACENT=True.

Результат: _parcel_full.jsonl (уникальные id) + _parcel_full.txt (читаемый).
Console не печатает кириллицу.
"""
import io
import json
import os
import sys
import time

import requests

KEY = os.environ.get("TWOGIS_API_KEY") or (
    sys.argv[1] if len(sys.argv) > 1 else "")
if not KEY:
    sys.exit("pass key or set TWOGIS_API_KEY")

ITEMS = "https://catalog.api.2gis.com/3.0/items"
HERE = os.path.dirname(os.path.abspath(__file__))
CITY = "70030076174471798"          # Душанбе
ALIAS = "dushanbe"
ADJACENT = False
FIELDS = ("items.point,items.address_name,items.name,items.full_name,"
          "items.rubrics,items.phones,items.adm_div,items.org")

CORE_RUBRICS = [
    ("335", u"Почта"),
    ("338", u"Экспресс-почта"),
    ("9741", u"Интиқоли байналмилалии бор"),
    ("417", u"Боркашонии автомобилии байнишаҳрӣ"),
    ("95584", u"Терминалҳои амонатӣ"),
    ("112611", u"Нуқтаҳои додани фармоишҳои интернетӣ"),
]
ADJ_RUBRICS = [
    ("423", u"Боркашонии роҳи оҳан"),
    ("402", u"Нақлиёти боркашонии ҳавоӣ"),
    ("5279", u"Анбори нигоҳдорӣ"),
    ("844", u"Барасмиятдарории гумрукӣ"),
]

# районы Душанбе, которые отдаёт 2ГИС (для дробления рубрик total>50)
DISTRICTS = [
    "70030077013570949",   # Сино
    "70030077013573846",   # Шоҳмансур
    "70030077013573016",   # Исмоили Сомонӣ
    "70030077013570227",   # Фирдавсӣ
]


def get(params):
    for attempt in range(5):
        try:
            r = requests.get(ITEMS, params={**params, "key": KEY}, timeout=60)
            j = r.json()
            code = (j.get("meta") or {}).get("code")
            if code in (429, 408) or r.status_code == 429:
                time.sleep(6 + 6 * attempt)
                continue
            return j
        except Exception:
            time.sleep(2 + 3 * attempt)
    return {"meta": {"code": 0}, "result": {"items": []}}


def rubric_names(item):
    out = []
    for r in item.get("rubrics") or []:
        if r.get("name"):
            out.append(r["name"])
    return out


def district(item):
    for a in item.get("adm_div") or []:
        if a.get("type") == "district":
            return a.get("name")
    return None


def enumerate_rubric(rid):
    """Все страницы рубрики; при total>50 дробим по районам (демо-ключ
    отдаёт не больше 50 карточек на одно окно rubric_id/page)."""
    seen = {}
    total = None

    def pump(extra):
        nonlocal total
        page = 1
        got = 0
        while True:
            p = {"rubric_id": rid, "city_id": CITY, "page_size": 10,
                 "page": page, "fields": FIELDS}
            p.update(extra)
            j = get(p)
            res = j.get("result") or {}
            if total is None:
                total = res.get("total")
            items = res.get("items") or []
            if not items:
                break
            for x in items:
                iid = str(x.get("id"))
                if iid and iid != "None":
                    seen[iid] = x
            got += len(items)
            cur = len(seen)
            if page >= 5 or cur >= int(total or 0):
                break
            page += 1
            time.sleep(0.3)

    pump({})
    if total and int(total) > 50 and len(seen) < int(total):
        for did in DISTRICTS:
            pump({"district_id": did})
            if len(seen) >= int(total):
                break
    return list(seen.values()), total


def main():
    rubrics = CORE_RUBRICS + (ADJ_RUBRICS if ADJACENT else [])
    fh = io.open(os.path.join(HERE, "_parcel_full.jsonl"), "w",
                 encoding="utf-8", newline="\n")
    txt = io.open(os.path.join(HERE, "_parcel_full.txt"), "w",
                  encoding="utf-8")
    by_id = {}
    per_rubric = {}
    for rid, rname in rubrics:
        items, total = enumerate_rubric(rid)
        per_rubric[rname] = {"total": total, "fetched": len(items)}
        for x in items:
            iid = str(x.get("id"))
            if not iid or iid == "None":
                continue
            pt = x.get("point") or {}
            org = x.get("org") or {}
            rec = by_id.get(iid)
            if rec is None:
                rec = {"id": iid,
                       "name": x.get("name") or x.get("full_name"),
                       "org_name": org.get("name"),
                       "branch_count": org.get("branch_count"),
                       "address": x.get("address_name"),
                       "district": district(x),
                       "lat": pt.get("lat"), "lon": pt.get("lon"),
                       "rubrics": rubric_names(x),
                       "phones": [p.get("number") for p in (x.get("phones") or [])],
                       "url": "https://2gis.tj/%s/firm/%s/" % (ALIAS, iid),
                       "in_rubrics": []}
                by_id[iid] = rec
            if rname not in rec["in_rubrics"]:
                rec["in_rubrics"].append(rname)
        print("rubric %s total=%s fetched=%s union=%d" % (
            rid, total, len(items), len(by_id)))
        time.sleep(0.5)
    # запись
    for rec in by_id.values():
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    fh.close()
    txt.write(u"Душанбе: уникальных карточек = %d\n" % len(by_id))
    for rname, d in per_rubric.items():
        txt.write(u"  рубрика %-40s total=%s fetched=%s\n" % (
            rname, d["total"], d["fetched"]))
    txt.write(u"\n================ список по id\n")
    for iid, rec in sorted(by_id.items(),
                           key=lambda kv: (kv[1]["name"] or u"")):
        txt.write(u"%s | %s | %s | %s,%s | тел=%s | %s | %s\n" % (
            rec["name"], rec["address"], u"/".join(rec["rubrics"][:2]),
            rec["lat"], rec["lon"],
            u";".join(rec["phones"]) or u"—", u"|".join(rec["in_rubrics"]),
            rec["url"]))
    txt.close()
    print("done unique=%d" % len(by_id))


if __name__ == "__main__":
    main()
