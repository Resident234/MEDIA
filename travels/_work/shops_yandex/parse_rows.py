# -*- coding: utf-8 -*-
"""Merge rows.jsonl (yx_lookup) into one deduplicated org table per city.

usage: python parse_rows.py

Ratings live in the snippet text as "Рейтинг | 4,1 | 17 оценок" (same layout
the fitness pass documented), coordinates come from data-coordinates as
"lon,lat". Rows with kind=org are single-card answers — their text is the
card body, not a snippet, but the same fields are parsed from it. Every
distinct /maps/org/ card is kept once per city (merged across queries, the
queries that found it are recorded in src). Output:
  all.tsv              every seen card, readable dump
  cards_input.jsonl    org cards worth opening for contacts (see priority),
                       the shape yx_cards.py consumes.
"""
import io
import json
import os
import re
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
RATING = re.compile(r"Рейтинг\s*\|\s*(\d+)[,.](\d+)")
ARIA = re.compile(r"Оценка (\d+[.,]\d+)")
REVIEWS = re.compile(r"(\d+)\s*(?:оценок|оценки|отзывов|отзыва|оценка)")
PRIORITY_QUERIES = {"базар", "рынок", "торговый центр", "супермаркет",
                    "гипермаркет", "интернет-магазин", "маркетплейс",
                    "пункт выдачи", "ремесла", "сувениры"}


def name_queries():
    """Queries from _plan.tsv that are not one of the category words — i.e. the
    concrete places named in раздел 8. Their cards are worth opening too."""
    path = os.path.join(HERE, "_plan.tsv")
    out = set()
    if os.path.exists(path):
        for line in io.open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            q = re.split(r"\t|\|", line)[-1].strip()
            if q not in CATEGORY_WORDS:
                out.add(q)
    return out


CATEGORY_WORDS = {"базар", "рынок", "торговый центр", "супермаркет",
                  "гипермаркет", "магазин", "дукон", "интернет-магазин",
                  "маркетплейс", "пункт выдачи", "ремесла", "сувениры"}


def card_id(href):
    """Org id from a /maps/org/<slug>/<id>/ link (works for relative and
    absolute hrefs; a kind=org row carries an absolute one)."""
    return (href or "").rstrip("/").split("/")[-1] or None


def full_url(href):
    href = href or ""
    if href.startswith("http"):
        return href
    return "https://yandex.kz" + href


ADDR_WORDS = (r"(ул\.|просп|наб\.|переулок|мкр|район|б-р|шоссе|кв\.|улица|кӯча|"
              r"маҳалла|ноҳия|деҳа|шаҳр)")
# Тело карточки у kind=org — это innerText всей страницы, в нём адрес идёт
# после слова «Адрес», а дальше — кнопки («Маршрут», «Как добраться»…).
ADDR_STOP = (r"(?:Маршрут|Как добраться|Показать|Открыто|Закрыто|Контакты|"
             r"Время работы|Особенности|Построить|Сайт|Телефон|\n|\||$)")
CAT_WORDS_RE = (r"(магазин|рынок|базар|центр|выдач|супермаркет|гипермаркет|"
                r"сувенир|ремесл|тӯҳфа|мағоза|продав|ярмарк)")


def flat(value):
    return " ".join(str(value).split()) if value else None


def addr_from(text):
    """Адрес из сниппета (поля разведены «|») или из тела карточки («Адрес …»)."""
    t = text or ""
    m = re.search(r"Адрес[:\s]\s*(.{3,140}?)\s*" + ADDR_STOP, t, re.S)
    if m:
        return flat(m.group(1))
    for p in [x.strip() for x in t.split("|")]:
        if len(p) <= 120 and re.search(ADDR_WORDS, p, re.I):
            return flat(p)
    return None


def parse_text(text):
    out = {"rating": None, "reviews": None, "addr": None, "cats": None}
    m = RATING.search(text or "")
    if m:
        out["rating"] = float("%s.%s" % (m.group(1), m.group(2)))
    m = REVIEWS.search(text or "")
    if m:
        out["reviews"] = int(m.group(1))
    out["addr"] = addr_from(text)
    parts = [p.strip() for p in (text or "").split("|")]
    for p in parts:
        if len(p) <= 70 and re.search(CAT_WORDS_RE, p, re.I) \
                and "Рейтинг" not in p and "оцен" not in p:
            out["cats"] = flat(p)
            break
    return out


def cell(value):
    """TSV-safe строка: текст сниппета — это innerText, в нём есть и переводы
    строк, и табы, и без них одна карточка разъезжается на несколько линий."""
    if value is None:
        return ""
    return " ".join(str(value).split())


# Яндекс доносит до выдачи карточки соседних стран, когда в городском каталоге
# ничего не найдено: по «Зелёный базар» из Душанбе — «Зелёный базар» Алматы
# (рейтинг 5,0 при 21834 оценках!), по «Пайшанба» — рынок в Сурхандарьинской
# области, а каталоги, которые резолвер прокинул на чужой город (Париу →
# Москва), отдают вообще чужие страны. Такие строки в справочник не идут: они
# не про Таджикистан, и молча оставить их — значит соврать про покрытие.
TJ_BOX = (66.95, 36.55, 75.15, 41.10)   # lon_min, lat_min, lon_max, lat_max
FOREIGN = re.compile(
    r"(Алматы|Алматин|Жетысуск|Талгар|Панфилов|Иссык|Чуйск|Кыргыз|Бишкек|"
    r"Каракол|Таласск|Жамбыл|Тараз|Шымкент|Туркестанск|Кзылорд|Актынск|"
    r"Ташкент|Наманган|Самарканд|Бухарск|Ферган|Андижан|Кашкадарьин|"
    r"Сурхандарьин|Хорезм|Каракалпак|Джизак|Сырдарьин|Навоийск|"
    r"Кабул|Афганистан|Кундуз|Баглан|Тахар|Хост|Кандагар|Мазари-Шариф|"
    r"Москва|Московск|Подольск|Краснодар|Ставропол)")


def outside_tajikistan(lat, lon, addr, text):
    """Причина отбраковки или None."""
    try:
        la, lo = float(lat), float(lon)
    except (TypeError, ValueError):
        la = lo = None
    if la is not None and not (TJ_BOX[1] <= la <= TJ_BOX[3] and
                               TJ_BOX[0] <= lo <= TJ_BOX[2]):
        return "out_of_box"
    probe = addr or (text or "")[:400]
    if FOREIGN.search(probe or ""):
        return "foreign_addr"
    return None


def main():
    names = name_queries()
    merged = OrderedDict()
    for line in io.open(HERE + "/rows.jsonl", encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        href = rec.get("href") or ""
        if "/maps/org/" not in href:
            continue
        # the same card arrives as a list snippet (relative href, id filled) and
        # as a kind=org single answer (absolute href, no id) — key on the id so
        # the two views merge instead of duplicating the row.
        key = (rec.get("city"), rec.get("id") or card_id(href))
        if key not in merged:
            merged[key] = {"city": rec.get("city"), "city_ru": rec.get("city_ru"),
                           "id": rec.get("id") or card_id(href), "href": href,
                           "name": rec.get("name"), "coords": rec.get("coords"),
                           "text": rec.get("text") or "", "src": [rec.get("query")]}
        else:
            m = merged[key]
            if rec.get("query") and rec["query"] not in m["src"]:
                m["src"].append(rec["query"])
            for f in ("name", "coords", "text"):
                if not m.get(f) and rec.get(f):
                    m[f] = rec[f]
            if not m.get("href") and href:
                m["href"] = href

    rows = []
    dropped = []
    for key, m in merged.items():
        p = parse_text(m["text"])
        if p["rating"] is None:
            a = ARIA.search(m["text"])
            if a:
                p["rating"] = float(a.group(1).replace(",", "."))
        coords = (m.get("coords") or "").split(",")
        lon, lat = (coords + ["", ""])[:2]
        href = m["href"] or ""
        cid = m["id"] or card_id(href)
        srcset = set(m["src"])
        reason = outside_tajikistan(lat, lon, p["addr"], m["text"])
        if reason:
            dropped.append({"city": m["city"], "name": m["name"], "why": reason,
                            "addr": p["addr"], "lat": lat, "lon": lon,
                            "src": "+".join(m["src"])})
            continue
        rows.append({"id": cid, "city": m["city"], "city_ru": m["city_ru"],
                    "name": m["name"], "url": full_url(href),
                    "lon": lon, "lat": lat, "rating": p["rating"],
                    "reviews": p["reviews"], "addr": p["addr"], "cats": p["cats"],
                    "src": "+".join(m["src"]),
                    "named": bool(srcset & names),
                    "priority": bool((PRIORITY_QUERIES & srcset) or (srcset & names))})

    with io.open(os.path.join(HERE, "all.tsv"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("city\tname\trating\treviews\taddr\tcats\tlat\tlon\tsrc\tnamed\t"
                 "priority\turl\n")
        for r in rows:
            fh.write("\t".join(cell(r[c]) for c in
                               ("city", "name", "rating", "reviews", "addr", "cats",
                                "lat", "lon", "src", "named", "priority", "url")) + "\n")
    want = [r for r in rows if r["priority"] and r["url"]]
    with io.open(os.path.join(HERE, "cards_input.jsonl"), "w", encoding="utf-8",
                 newline="\n") as fh:
        for r in want:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"cards_total": len(rows), "cards_org": sum(1 for r in rows if r["id"]),
                      "priority": len(want), "named": sum(1 for r in rows if r["named"]),
                      "dropped_non_tj": len(dropped),
                      "rated": sum(1 for r in rows if r["rating"] is not None),
                      "no_rating": sum(1 for r in rows if r["rating"] is None)},
                     ensure_ascii=True))
    with io.open(os.path.join(HERE, "parse_stats.json"), "w", encoding="utf-8",
                 newline="\n") as fh:
        json.dump({"cards_total": len(rows),
                   "cards_org": sum(1 for r in rows if r["id"]),
                   "priority": len(want),
                   "named": sum(1 for r in rows if r["named"]),
                   "rated": sum(1 for r in rows if r["rating"] is not None),
                   "dropped": len(dropped),
                   "drop_whys": {w: sum(1 for d in dropped if d["why"] == w)
                                 for w in set(d["why"] for d in dropped)},
                   "drop_samples": dropped[:20]},
                  fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
