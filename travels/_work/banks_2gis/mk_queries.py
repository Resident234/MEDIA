# -*- coding: utf-8 -*-
"""Собрать список улиц/районов Душанбе для расширения аптечной выдачи 2ГИС.

usage: python mk_queries.py

API 2ГИС закрыт для обоих ключей, браузер — капча, поэтому живой канал только
SSR-выдача `2gis.tj/dushanbe/search/<запрос>`, где лежит ровно 12 карточек из
`total`. Проверено probe_facets.py: фильтры, сортировки и `page` сервер
игнорирует (те же 12), а вот ТЕКСТ запроса набор меняет — «аптека <район>»
давала по 6-11 новых id. Значит полный список Душанбе (1084 аптеки) собирается
шириной: много узких запросов, объединение первых страниц.

Улица — идеальный срез: аптек на улице обычно 1-6, то есть все они попадают в
12 карточек ответа. Названия улиц брать не из головы, а из уже снятого
массива 2ГИС (shops_2gis/items_all.json: 2016 карточек Душанбе с адресами) —
получается честный список того, как улицы называются в этом же справочнике.

Адреса в массиве бывают двух видов: дикт с `components[0].type=="location"`
(там только город) и живая строка вида `кӯчаи Шевченко, 32/13`. Улица
интересует именно из строки. Таджикские префиксы: `кӯчаи` (улица),
`хиёбони` (проспект), `маҳаллаи` (жилй массив/квартал); русские — `ул.`,
`улица`, `проспект`, `б-р`, `наб.`.

Выход: `_queries.txt`, базовые слова + районы + «аптека <улица>» по всем
улицам, извлечённым из строковых адресов.
"""
import io
import json
import os
import re
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SHOPS = os.path.join(HERE, "..", "shops_2gis")

# Префиксы уличных типов (таджикские + русские), после них идёт название.
STREET_PREFIX = re.compile(
    u"^\\s*(кӯчаи|кучаи|хиёбони|маҳаллаи|махаллаи|ул\\.|улица|проспект|просп\\b|"
    u"б-р|наб\\.|шоссе|переулок)\\s+(.+?)\\s*(?:,|\\s\\d|$)",
    re.UNICODE | re.IGNORECASE)
# Хвосты, которые прилипают к названию: «роғ», «шоссе» и т.п.
TAIL_CLEAN = re.compile(
    u"\\s*(роғ|шоссе|кӯча|проспект|переулок|бул.\\s*)$", re.UNICODE | re.IGNORECASE)
# Название улицы годится, если содержит хотя бы 3 буквы (кириллица/латиница).
LETTER_RE = re.compile(u"[\u0400-\u04FFa-zA-Z]{3,}", re.UNICODE)

BASE_WORDS = [u"банки", u"банк", u"обмен валют", u"валютный обмен",
              u"отделение банка", u"офис банка", u"банкомат",
              # Крупные Tajik banks (2GIS различает текстовые запросы)
              u"Амонатбанк", u"Амонатбонк", u"Amonatbank",
              u"Алина Банк", u"Alifa Bank", u"Алиф Банк",
              u"Спаталинбанк", u"Spitalin Bank", u"Спитакен",
              u"Мехргонбанк", u"Mehrgan Bank", u"Меҳргонбонк",
              u"Элтерсан", u"IQT", u"Элтерсан Банк",
              u"Банк Омдд", u"Omdad Bank", u"Умедбанк",
              u"Коммерцбанк Таджикистана", u"КБТ",
              u"Сохтмонбонк", u"Соҳтмонбонк", u"NBT",
              u"Точиксодиротбонк", u"Tojisomonбонк",
              u"Давонон", u"Давононбанк", u"Пайванд Банк",
              u"Фондбанк", u"Эсхатбанк", u"Арванд Банк",
              u"Парасбанк", u"Бонуди Хайр", u"Киштхалозбонк"]
DISTRICTS = [u"Исмоили Сомони", u"Фирдоуси", u"Сино", u"Шохмансур",
             u"Центральный", u"Фирдавси", u"Рудаки", u"Абу-али Ибн Сино",
             u"Гиссарский район", u"Вахдат", u"Парвас", u"Носири Хусрав"]


def extract_street(s):
    """Из строки адреса — название улицы (или None)."""
    if not s or not isinstance(s, str):
        return None
    m = STREET_PREFIX.match(s)
    if not m:
        return None
    name = m.group(2).strip()
    # Хвостовые «роғ», «шоссе» и т. п.
    prev = None
    while prev != name:
        prev = name
        name = TAIL_CLEAN.sub("", name).strip()
    # Срезать номера домов, если вдруг прилипли
    name = re.sub(u"[,\\s]+\\d+[а-яА-Яa-zA-Z/\\-]*$", "", name).strip()
    if len(name) < 3:
        return None
    if not LETTER_RE.search(name):
        return None
    return name


def load_streets():
    """Counter<street> по строковым адресам из items_all.json."""
    path = os.path.join(SHOPS, "items_all.json")
    data = json.load(io.open(path, encoding="utf-8"))
    items = data if isinstance(data, list) else []
    streets = Counter()
    str_hits = 0
    for it in items:
        ad = it.get("address")
        s = None
        if isinstance(ad, str):
            s = ad
        elif isinstance(ad, dict):
            # иногда street живёт в components[].type=="street"
            for c in ad.get("components") or []:
                if isinstance(c, dict) and c.get("type") == "street":
                    streets[c.get("street") or c.get("comment")] += 1
            s = ad.get("unified") or ad.get("value") or ad.get("full_name")
        nm = extract_street(s) if s else None
        if nm:
            streets[nm] += 1
            str_hits += 1
    # District-поле даёт ещё срез: часто заполнено явно.
    dists = Counter()
    for it in items:
        d = it.get("district")
        if isinstance(d, str) and d.strip():
            dists[d.strip()] += 1
    return streets, dists, len(items), str_hits


def main():
    streets, dists, n, hits = load_streets()
    print("items", n, "street-hits", hits, "distinct streets", len(streets),
          "distinct districts", len(dists))
    top_s = [s for s, c in streets.most_common(10)]
    top_d = [s for s, c in dists.most_common(10)]
    print("top streets:", json.dumps(top_s, ensure_ascii=True))
    print("top dists:", json.dumps(top_d, ensure_ascii=True))
    ranked = [s for s, _ in streets.most_common()]
    lines = []
    for w in BASE_WORDS:
        lines.append(w)
    for d in DISTRICTS:
        lines.append(u"банки " + d)
    # Дополнительные районы, если их не было в фикс-списке
    lower = set(x.lower() for x in DISTRICTS)
    for d in [x for x, _ in dists.most_common() if x.lower() not in lower]:
        lines.append(u"банки " + d)
    for s in ranked:
        lines.append(u"банк " + s)
    # Крупные банки × районы (2GIS различает текстовые запросы, total=831
    # по "банки" не всегда раскрывает филиалы — добавляем срезы).
    for op in (u"Амонатбанк", u"Алина", u"Спаталин", u"Мехргонбанк",
               u"Элтерсан", u"Омдд", u"Сохтмонбонк", u"КБТ",
               u"Давонон", u"Фондбанк", u"Эсхатбанк", u"Арванд",
               u"Парасбанк", u"Точиксодиротбонк"):
        for d in DISTRICTS:
            lines.append(op + u" " + d)
    # Дедупликация с сохранением порядка
    seen = set()
    uniq = []
    for l in lines:
        k = l.strip().lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(l)
    path = os.path.join(HERE, "_queries.txt")
    io.open(path, "w", encoding="utf-8", newline="\n").write(
        "\n".join(uniq) + "\n")
    io.open(os.path.join(HERE, "_streets.json"), "w", encoding="utf-8").write(
        json.dumps(ranked, ensure_ascii=False, indent=1))
    print("queries:", len(uniq),
          "(%d base, %d dists, %d streets)" % (
              len(BASE_WORDS), len(DISTRICTS), len(ranked)))
    print(json.dumps({"items": n, "streets": len(ranked),
                      "queries": len(uniq)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
