# -*- coding: utf-8 -*-
"""Собрать план аптечного прогона: каталог города × аптечный запрос.

usage: python mk_plan.py

Каталоги берутся из `_cityids.json` (его заполнил yx_cityids.py ещё в прогоне
по покупкам: название города -> `id/slug` справочника Яндекса) плюс пять
крупных городов, чьи каталоги были записаны вручную. Чужие каталоги
(`10090/afghanistan`, `213/moscow`) отсекаются: у Яндекса они резолвятся из
таджикских названий, но карточки там не про Таджикистан, и в разделе 8 такие
строки уже отбраковывались по границам страны.

Запросы лежат в `_queries.txt` (одна строка на запрос): кириллица в аргументах
PowerShell искажается, поэтому список — файлом, а не параметром.

На выходе `_plan.tsv` вида `city_slug|query`: 16 каталогов × 10 запросов.
Отдельно печатается, сколько каталогов и пар получилось, — это число потом
идёт в прозу раздела как заявленный объём работы.
"""
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# Крупные города, каталоги которых известны заранее (прогон по покупкам).
# В `_cityids.json` их нет — названия резолвер Яндекса возвращает криво, и эти
# пять каталогов были записаны руками в yx_lookup.py (таблица EXTRA).
MANUAL = {
    "dushanbe": ("10318", "Душанбе"),
    "khujand": ("10322", "Худжанд"),
    "bohtar": ("10319", "Бохтар"),
    "kulob": ("20882", "Куляб"),
    "tursunzoda": ("21107", "Турсунзаде"),
}
ORDER_FIRST = ["dushanbe", "khujand", "bohtar", "kulob", "tursunzoda"]
# Чужие каталоги: резолвер Яндекса ведёт на них из таджикских названий.
FOREIGN = ("afghanistan", "moscow", "kabul")


def catalogs():
    """slug -> (id, русское название): ручной список плюс то, что разрезолвилось.

    Имя из `_cityids.json` берётся только если для слага нет ручной пары: в
    файле под одним slug лежат несколько названий-синонимов (города, которые
    резолвер привязал к одному каталогу), и первое по алфавиту выходит кривым.
    """
    out = {}
    for slug, (cid, ru) in MANUAL.items():
        out[slug] = (cid, ru)
    path = os.path.join(HERE, "_cityids.json")
    data = json.load(io.open(path, encoding="utf-8"))
    for name, got in sorted(data.items()):
        for cat in ((got or {}).get("cats") or []):
            cid, slug = cat.split("/")
            if any(f in slug for f in FOREIGN):
                continue
            if slug not in out:
                out[slug] = (cid, name)
    return out


def main():
    cats = catalogs()
    queries = [l.strip() for l in io.open(os.path.join(HERE, "_queries.txt"),
                                          encoding="utf-8") if l.strip()]
    print("catalogs:", len(cats), "queries:", len(queries))
    for slug, (cid, ru) in sorted(cats.items()):
        print("  %-45s %s  %s" % (slug, cid, json.dumps(ru, ensure_ascii=True)))
    lines = [u"# city_slug|query — список аптек по всем таджикским каталогам Яндекса"]
    # Душанбе и крупные города идут первыми: если прогон прервётся на троттлинге,
    # самая нужная часть массива уже будет снята.
    order = [s for s in ORDER_FIRST if s in cats] + \
            sorted(s for s in cats if s not in ORDER_FIRST)
    for slug in order:
        for q in queries:
            lines.append("%s|%s" % (slug, q))
    path = os.path.join(HERE, "_plan.tsv")
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    print("pairs:", len(lines) - 1, "->", os.path.basename(path))
    print(json.dumps({"catalogs": len(cats), "queries": len(queries),
                      "pairs": len(lines) - 1}, ensure_ascii=True))


if __name__ == "__main__":
    main()
