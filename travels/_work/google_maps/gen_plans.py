# -*- coding: utf-8 -*-
"""Generate plans/<domain>.tsv for the Google Maps collectors.

Uses the same 44-city scope as travels/_work/housing_yandex/cities.py plus the
per-domain query lists harvested from the existing Yandex collectors. Output
line format matches run_domain.py's loader:

    slug<TAB>lat,lon<TAB>query1;query2;...

`near` = `lat,lon` is fed to GM as `/@lat,lon,14z/` so small-town catalogs
resolve even when the query text is ambiguous. Dushanbe and the four other
major cities come first so a killed run still leaves the useful core done.
"""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PLANS = os.path.join(HERE, "plans")
os.makedirs(PLANS, exist_ok=True)

# 44 cities: (slug, lat, lon) — same scope as housing_yandex/cities.py,
# ordered so the biggest catalogs come first.
CITIES = [
    ("dushanbe",     38.5598, 68.7870),
    ("khujand",      40.2839, 69.6287),
    ("bohtar",       37.8400, 68.7800),
    ("kulob",        37.9100, 69.7800),
    ("tursunzoda",   38.5140, 68.2330),
    ("vahdat",       38.5530, 69.0200),
    ("hisor",        38.5260, 68.5500),
    ("isfara",       40.1200, 69.7000),
    ("istaravshan",  39.9100, 69.0000),
    ("konibodom",    40.2800, 70.3000),
    ("pendjikent",   39.5000, 67.6000),
    ("nurek",        38.3900, 69.3300),
    ("rogun",        38.7800, 69.8700),
    ("panj",         37.3000, 69.1000),
    ("vakhsh",       37.7000, 69.0000),
    ("horog",        37.4900, 71.5500),
    ("murghob",      38.1700, 73.9700),
    ("rashtdan",     39.0200, 70.3800),
    ("bares",        38.2000, 72.5000),        # Darvoz district center
    ("shahrituz",    37.3000, 68.1000),
    ("kubodiyon",    37.4000, 68.4000),
    ("levakant",     37.7500, 68.8300),
    ("dusti",        37.3000, 68.6000),
    ("jayhun",       37.5000, 69.0000),
    ("khuroson",     37.8000, 68.9000),
    ("muminobod",    37.9000, 70.1000),
    ("khovaling",    38.4000, 70.0000),
    ("baljuvon",     38.3000, 70.0000),
    ("vose",         37.9000, 69.8000),
    ("farkhor",      37.6000, 69.4000),
    ("kushoniyon",   37.8500, 68.8000),
    ("shahrinaw",    38.5700, 68.3300),
    ("rudaki",       38.4500, 68.7500),
    ("varzob",       38.7500, 68.7500),
    ("faizobod",     38.5500, 69.3200),
    ("nurobod",      38.9000, 69.7500),
    ("tojikobod",    38.7000, 69.9000),
    ("lakhsh",       38.9000, 71.5000),
    ("dangara",      38.1000, 69.3000),
    ("temurmalik",   38.2000, 69.9000),
    ("nosiri",       37.3000, 70.5000),
    ("buston",       40.1900, 69.6600),
    ("guliston_sogd",40.2400, 69.7800),
    ("asht",         40.7000, 70.2000),
    ("zafarobod",    40.0000, 68.9000),
    ("mastchoh",     40.5000, 69.3000),
    ("spitamen",     40.3000, 69.5000),
    ("rasulov",      40.6000, 69.1000),
    ("devashtich",   40.1000, 68.7000),
    ("ishkoshim",    36.7200, 71.6000),
    ("roshtkala",    37.4000, 71.4000),
    ("shugnan",      37.6000, 71.7000),
    ("rushan",       37.9000, 71.6000),
    ("vanch",        38.3000, 71.9000),
    ("darvoz",       38.4700, 70.9000),
]

# Per-domain queries. Trimmed versions of the Yandex `_queries.txt` lists
# (dropping obvious no-result variants). All names are in Russian, matching
# the way the existing Yandex blocks were collected; GM's catalog returns
# bilingual (ru+tg) places regardless.
DOMAINS = {
    "fitness": [
        u"Тренажерный зал", u"Фитнес", u"Йога", u"Бассейн",
        u"Спортивный зал", u"Кроссфит",
    ],
    "housing": [
        u"Гостиница", u"Гостевой дом", u"Квартиры посуточно", u"Отель",
        u"Хостел", u"Апартаменты", u"Меҳмонхона", u"Турбаза", u"Кемпинг",
    ],
    "food": [
        u"Кафе", u"Ресторан", u"Бар", u"Чайхана", u"Кофейня", u"Паб",
        u"Фудкорт", u"Доставка еды", u"Пиццерия", u"Суши", u"Шаурма",
        u"Лагман", u"Шашлык", u"Столовая", u"Быстрое питание", u"Фастфуд",
        u"Кальян", u"Ночной клуб",
    ],
    "shops": [
        u"Супермаркет", u"Торговый центр", u"Гипермаркет", u"Рынок",
        u"Магазин продуктов", u"Мини-маркет", u"Универмаг", u"Базар",
    ],
    "pharma": [
        u"Аптека", u"Дорухона", u"Аптечный пункт", u"Круглосуточная аптека",
        u"Аптека 24 часа", u"Лекарства", u"Фармация", u"Аптечная сеть",
        u"Ветеринарная аптека", u"Аптека оптовые цены",
    ],
    "labs": [
        u"Лаборатория", u"Медицинская лаборатория", u"Лаборатория анализов",
        u"Анализы", u"Диагностика", u"Диагностический центр", u"ПЦР",
        u"ИФА", u"УЗИ", u"Забор анализов",
    ],
    "telecom": [
        u"Tcell", u"МегаФон Таджикистан", u"Зет-Мобайл", u"Бабилон-Т",
        u"Тоҷиктелеком", u"Салон связи", u"Оператор связи", u"SIM-карта",
        u"Anor", u"Мобилл+", u"Истиклол Телеком",
    ],
    "banks": [
        u"Банк", u"Отделение банка", u"Банкомат", u"Обмен валюты",
        u"Платежный терминал", u"Элкарт", u"Милисат", u"Аримит",
        u"Душанбе-Сити-Банк", u"Амонатбанк", u"Ориенто Финанс",
        u"Спитамен", u"Имонбонк", u"Банки тоҷикӣ",
    ],
}


def write_plan(name, queries):
    path = os.path.join(PLANS, name + ".tsv")
    lines = [u"# %s: %d cities x %d queries -> %d rows" %
             (name, len(CITIES), len(queries), len(CITIES))]
    # one row per city, all queries on the same line semicolon-separated so
    # run_domain.py's load_plan expands them into (slug, near, q) triples
    qstr = ";".join(queries)
    for slug, lat, lon in CITIES:
        lines.append(u"%s\t%.4f,%.4f\t%s" % (slug, lat, lon, qstr))
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    print("wrote %s  (%d rows x %d queries = %d searches)" %
          (os.path.basename(path), len(CITIES), len(queries), len(CITIES) * len(queries)))


def main():
    for name, qs in DOMAINS.items():
        write_plan(name, qs)
    total = sum(len(CITIES) * len(qs) for qs in DOMAINS.values())
    print("\nTotal searches across all domains:", total)
    print("Estimated unique cards (assume ~90 per search, 20%% overlap):",
          int(total * 90 * 0.8))
    print("Estimated runtime at 300s/search + 12s/card:",
          "%.1f days continuous" % ((total * 300 + total * 90 * 0.8 * 12) / 86400))


if __name__ == "__main__":
    main()
