# -*- coding: utf-8 -*-
"""Сколько аптек уже лежит в собранном для раздела 8 массиве 2ГИС.

usage: python reuse_check.py

Раздел 8 собирал Душанбе по запросам про магазины и рубрикам про
супермаркеты/ПВЗ/сувениры; аптеки там не были целью. Но часть карточек
попадает в выборку случайно (текстовый запрос «магазин» находит «магазин
медтехники», рубрики у организации бывают дополнительные), а SSR-контакты к
ним уже сняты. Rubric «Аптеки» в таджикском каталоге имеет id 207 (alias
`apteki`, parent 5) — выяснено на выдаче 2gis.tj. Скрипт ищет:

1. в items_all.json записи с rubric_ids, где есть 207, и записи, у которых в
   названии корень «аптек»/«дорухон»/«фарм»;
2. для найденных id — есть ли уже снятая SSR-карточка в ssr_cards.jsonl и
   лежат ли в ней часы работы/телефон/сайт;
3. что из полей SSR-карточки вообщегодно использовать как источник часов —
   на случай, если аптеки придётся снимать заново.

Ответ ASCII-escaped.
"""
import io
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SHOPS = os.path.join(HERE, "..", "shops_2gis")
PHARM_RUBRIC = "207"
NAME_RE = re.compile(u"(?i)(аптек|дорухон|фарм|pharm|apteka)")


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def load_items():
    p = os.path.join(SHOPS, "items_all.json")
    d = json.load(io.open(p, encoding="utf-8"))
    if isinstance(d, dict):
        for k in ("items", "data", "rows"):
            if k in d:
                return d[k]
        # словарь id->item?
        out = []
        for k, v in d.items():
            if isinstance(v, dict):
                v.setdefault("id", k)
                out.append(v)
        return out
    return d


def rubric_ids(item):
    r = item.get("rubric_ids") or item.get("rubrics") or []
    out = set()
    for x in r:
        if isinstance(x, dict):
            out.add(str(x.get("id") or x.get("short_id") or ""))
        else:
            out.add(str(x))
    return out


def main():
    items = load_items()
    print("items in shops array:", len(items))
    by_rubric, by_name = [], []
    for it in items:
        rid = rubric_ids(it)
        if PHARM_RUBRIC in rid or "110179" in rid:
            by_rubric.append(it)
        if NAME_RE.search(it.get("name") or ""):
            by_name.append(it)
    print("с рубрикой аптек:", len(by_rubric))
    print("с корнем аптека/дорухон/фарм в названии:", len(by_name))
    ids = set(str(i.get("id")) for i in by_rubric + by_name)
    print("уникальных id:", len(ids))
    sample = (by_rubric + by_name)[:6]
    for s in sample:
        print("  ", ascii_(json.dumps({"id": s.get("id"), "name": s.get("name"),
                                       "addr": (s.get("address") or {}).get("value")
                                       if isinstance(s.get("address"), dict) else s.get("address"),
                                       "point": s.get("point") or s.get("geometry"),
                                       "rubrics": sorted(rubric_ids(s))},
                                      ensure_ascii=True))[:260])
    # что есть в SSR-карточках
    ssr = {}
    p = os.path.join(SHOPS, "ssr_cards.jsonl")
    for line in io.open(p, encoding="utf-8"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        ssr[str(d.get("id") or d.get("firm_id") or "")] = d
    print("ssr cards:", len(ssr))
    have = [i for i in ids if i in ssr]
    print("из них уже снято карточек:", len(have))
    if ssr:
        any_card = next(iter(ssr.values()))
        print("поля ssr-карточки:", ascii_(sorted(any_card.keys()))[:600])
        sched = [k for k in any_card if re.search(r"(?i)(hour|schedule|time|график|время)", k)]
        print("поля про часы:", ascii_(sched))
        print("пример:", ascii_(json.dumps({k: any_card[k] for k in list(any_card)[:12]},
                                           ensure_ascii=True))[:700])
    hits = [i for i in have if re.search(r"(?i)(hour|schedule)", json.dumps(ssr[i]))]
    print("ssr-карточек с расписанием среди найденных аптечных:", len(hits))
    io.open(os.path.join(HERE, "reuse_pharm_ids.json"), "w", encoding="utf-8").write(
        json.dumps(sorted(ids), indent=1))


if __name__ == "__main__":
    main()
