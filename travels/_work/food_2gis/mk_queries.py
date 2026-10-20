# -*- coding: utf-8 -*-
"""Список запросов для съёма food-заведений 2ГИС по Душанбе.

usage: python mk_queries.py

Канал тот же, что в pharma_2gis/labs_2gis: SSR-выдача `2gis.tj/dushanbe/
search/<q>` отдаёт 12 карточек, полный список собирается шириной — много
узких запросов, union по id.

Три оси запросов:
  1) базовые слова по каждой категории (кафе/бар/ресторан/чайхана/кофейня/
     паб/фудкорт/доставка еды/пиццерия/суши/шаурма/лагман/шашлык/кальян/
     стоповая/кондитерская/быстрое питание/дискотека/клуб/караоке);
  2) «<категория> <район>» — 4 основные категории × 12 районов;
  3) «<категория> <улица>» — 3 основные категории (кафе/бар/ресторан) ×
     все 179 улиц, извлечённых из shops_2gis/items_all.json.

Выход: `_queries.txt`, по строке на запрос.
"""
import io
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SHOPS = os.path.join(HERE, "..", "shops_2gis")
sys.path.insert(0, os.path.join(HERE, "..", "pharma_2gis"))

STREET_PREFIX = re.compile(
    u"^\\s*(кӯчаи|кучаи|хиёбони|маҳаллаи|махаллаи|ул\\.|улица|проспект|просп\\b|"
    u"б-р|наб\\.|шоссе|переулок)\\s+(.+?)\\s*(?:,|\\s\\d|$)",
    re.UNICODE | re.IGNORECASE)
TAIL_CLEAN = re.compile(
    u"\\s*(роғ|шоссе|кӯча|проспект|переулок|бул.\\s*)$", re.UNICODE | re.IGNORECASE)
LETTER_RE = re.compile(u"[\u0400-\u04FFa-zA-Z]{3,}", re.UNICODE)

BASE_WORDS = [
    u"кафе", u"бар", u"ресторан", u"чайхана", u"кофейня", u"паб",
    u"фудкорт", u"фуд-корт", u"доставка еды", u"пиццерия", u"суши",
    u"шаурма", u"лагман", u"шашлык", u"кальян", u"столовая",
    u"кондитерская", u"быстрое питание", u"дискотека", u"ночной клуб",
    u"караоке", u"кофейни", u"чойхона", u"кафешка", u"закусочная",
    u"фастфуд", u"бургерная", u"пекарня", u"пекарня-кафе", u"дхонер",
    u"ресторан быстрого питания", u"доставка",
]

# По этим категориям расширяем по всем районам и всем улицам — они дают
# основную массу карточек. Остальные слова идут только в base.
BROAD_CATS = [u"кафе", u"бар", u"ресторан"]
DISTRICT_ONLY = [u"кафе", u"бар", u"ресторан", u"чайхана"]

DISTRICTS = [u"Исмоили Сомони", u"Фирдоуси", u"Сино", u"Шохмансур",
             u"Центральный", u"Фирдавси", u"Рудаки", u"Абу-али Ибн Сино",
             u"Гиссарский район", u"Вахдат", u"Парвас", u"Носири Хусрав"]


def extract_street(s):
    if not s or not isinstance(s, str):
        return None
    m = STREET_PREFIX.match(s)
    if not m:
        return None
    name = m.group(2).strip()
    prev = None
    while prev != name:
        prev = name
        name = TAIL_CLEAN.sub("", name).strip()
    name = re.sub(u"[,\\s]+\\d+[а-яА-Яa-zA-Z/\\-]*$", "", name).strip()
    if len(name) < 3:
        return None
    if not LETTER_RE.search(name):
        return None
    return name


def load_streets():
    path = os.path.join(SHOPS, "items_all.json")
    data = json.load(io.open(path, encoding="utf-8"))
    items = data if isinstance(data, list) else []
    streets = Counter()
    for it in items:
        ad = it.get("address")
        s = None
        if isinstance(ad, str):
            s = ad
        elif isinstance(ad, dict):
            for c in ad.get("components") or []:
                if isinstance(c, dict) and c.get("type") == "street":
                    streets[c.get("street") or c.get("comment")] += 1
            s = ad.get("unified") or ad.get("value") or ad.get("full_name")
        nm = extract_street(s) if s else None
        if nm:
            streets[nm] += 1
    return streets


def main():
    streets = load_streets()
    ranked = [s for s, _ in streets.most_common()]
    lines = list(BASE_WORDS)
    for cat in DISTRICT_ONLY:
        for d in DISTRICTS:
            lines.append(u"%s %s" % (cat, d))
    for cat in BROAD_CATS:
        for s in ranked:
            lines.append(u"%s %s" % (cat, s))
    # Дедуп, сохраняя порядок.
    seen, uniq = set(), []
    for l in lines:
        k = l.strip().lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(l)
    out = os.path.join(HERE, "_queries.txt")
    io.open(out, "w", encoding="utf-8", newline="\n").write(
        "\n".join(uniq) + "\n")
    print("queries:", len(uniq),
          "(base=%d, district-pairs=%d, street-pairs=%d, streets=%d)" % (
              len(BASE_WORDS), len(DISTRICT_ONLY) * len(DISTRICTS),
              len(BROAD_CATS) * len(ranked), len(ranked)))


if __name__ == "__main__":
    main()
