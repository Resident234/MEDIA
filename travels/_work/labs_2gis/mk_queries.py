# -*- coding: utf-8 -*-
"""Список запросов для съёма лабораторий/анализов 2ГИС по Душанбе.

usage: python mk_queries.py

Идея та же, что в pharma_2gis/mk_queries.py: SSR-выдача `2gis.tj/dushanbe/
search/<q>` отдаёт ровно 12 карточек, пагинацию/фильтры сервер игнорирует,
поэтому полный список собирается шириной — много узких запросов, union по id.

Для лабораторий три оси:
  1) базовые слова: лаборатория / анализы / диагностика / ПЦР / ИФА /
     экспресс-тест + таджикские варианты (таҳлил, озмуни тиббӣ);
  2) названия сетей — федеральных (Инвитро/Хеликс/Гемотест/Синэво/ЛабКвест)
     и местных (Ориён Лаб, Ситора, Поир, Ибн Сино, Рухсора);
  3) «лаборатория <район>» и «лаборатория <улица>» — улицы берутся из уже
     снятого массива shops_2gis/items_all.json (179 уник. названий).

Выход: `_queries.txt` — по строке на запрос.
"""
import io
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
PHARMA = os.path.join(HERE, "..", "pharma_2gis")
SHOPS = os.path.join(HERE, "..", "shops_2gis")
sys.path.insert(0, PHARMA)

# Те же префиксы, что в pharma/mk_queries.py.
STREET_PREFIX = re.compile(
    u"^\\s*(кӯчаи|кучаи|хиёбони|маҳаллаи|махаллаи|ул\\.|улица|проспект|просп\\b|"
    u"б-р|наб\\.|шоссе|переулок)\\s+(.+?)\\s*(?:,|\\s\\d|$)",
    re.UNICODE | re.IGNORECASE)
TAIL_CLEAN = re.compile(
    u"\\s*(роғ|шоссе|кӯча|проспект|переулок|бул.\\s*)$", re.UNICODE | re.IGNORECASE)
LETTER_RE = re.compile(u"[\u0400-\u04FFa-zA-Z]{3,}", re.UNICODE)

BASE_WORDS = [
    u"лаборатория", u"лаборатории", u"медицинская лаборатория",
    u"клиническая лаборатория", u"клинико-диагностическая лаборатория",
    u"лаборатория анализов", u"анализы", u"анализы крови", u"анализы мочи",
    u"гормональные анализы", u"онкомаркеры", u"общий анализ крови",
    u"биохимия крови", u"коагулограмма", u"алергопанель",
    u"диагностика", u"медицинская диагностика", u"диагностический центр",
    u"диагностическая лаборатория", u"функциональная диагностика",
    u"УЗИ", u"УЗД", u"ЭКГ", u"ЭХО", u"флюорография", u"МРТ", u"КТ",
    u"ПЦР", u"ПЦР-диагностика", u"ИФА", u"ИФА-диагностика",
    u"экспресс-тест", u"экспресс-диагностика", u"цитология", u"гистология",
    u"забор анализов", u"лабораторные исследования",
    u"медосмотр", u"медицинское обследование", u"check-up",
    u"инвитро", u"хеликс", u"гемотест", u"синэво", u"лабквест",
    u"Колымбо", u"лаборатория Ориён", u"Ориён Лаб", u"Ситора Лаб",
    u"Ибн Сино лаборатория", u"лаборатория Поир",
    u"таҳлил", u"таҳлили хун", u"таҳлилҳои тиббӣ",
    u"озмуни тиббӣ", u"лабораторияи тиббӣ", u"laboratoriya",
]

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
    lines = []
    for w in BASE_WORDS:
        lines.append(w)
    for d in DISTRICTS:
        lines.append(u"лаборатория " + d)
    for s in ranked:
        lines.append(u"лаборатория " + s)
    # Второй проход с другим маркером — ловим те, что не попали под слово
    # «лаборатория» (например, диагностические центры на той же улице).
    for s in ranked[:60]:
        lines.append(u"анализы " + s)
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
          "(base=%d, dists=%d, streets=%d, streets2=%d)" % (
              len(BASE_WORDS), len(DISTRICTS), len(ranked), min(60, len(ranked))))


if __name__ == "__main__":
    main()
