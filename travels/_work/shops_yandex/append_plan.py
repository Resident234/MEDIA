# -*- coding: utf-8 -*-
"""Append the countrywide category pass to _plan.tsv.

Reads _cityids.json (filled by yx_cityids.py) plus the five catalogs already
hard-coded in yx_lookup.py, and appends `city_slug|query` lines for every
catalog-owned city × the category words the request names. Idempotent: pairs
already present in _plan.tsv are not repeated. Cities whose resolution only
found the Dushanbe catalog (no city of their own) are skipped here and land
in _no_cover.json instead — that is an evidenced coverage answer, not a gap.

usage: python append_plan.py
"""
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
QUERIES = ["базар", "рынок", "торговый центр", "супермаркет",
           "гипермаркет", "магазин", "дукон", "интернет-магазин",
           "маркетплейс", "пункт выдачи", "ремесла", "сувениры"]
EXTRA_SLUGS = {  # already known catalogs, keyed as yx_lookup's EXTRA
    "Душанбе": "dushanbe", "Худжанд": "khujand", "Бохтар": "bohtar",
    "Куляб": "kulob", "Турсунзаде": "tursunzoda",
}


def main():
    path = os.path.join(HERE, "_cityids.json")
    ids = json.load(io.open(path, encoding="utf-8")) if os.path.exists(path) else {}
    owned, no_cover = {}, {}
    BAD = ("/afghanistan", "/moscow", "/jirgatol-district")
    # Геокодер Яндекса подкидывает чужие карточки: Париу — Москва, Ишкашим и
    # Файзабад — афганские города, Лахш — Джиргатольский район. Такие находки
    # не считаются таджикским каталогом и уходят в no_cover.
    for name, got in ids.items():
        cats = (got or {}).get("cats") or []
        own = [c for c in cats
               if not c.endswith("/dushanbe") and not any(c.endswith(b) for b in BAD)]
        if own:
            # Городские каталоги приоритетнее областных/районных: слаг города
            # даёт поиск в граница города, область — по всей области.
            city = [c for c in own if "province" not in c and "district" not in c]
            chosen = (city or own)[0]
            owned[name] = chosen.split("/")[1]
        else:
            no_cover[name] = got
    for name, slug in EXTRA_SLUGS.items():
        owned.setdefault(name, slug)

    plan_path = os.path.join(HERE, "_plan.tsv")
    existing = set()
    if os.path.exists(plan_path):
        for line in io.open(plan_path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.replace("\t", "|").split("|")
                existing.add((parts[0], parts[1]))

    added = []
    with io.open(plan_path, "a", encoding="utf-8", newline="\n") as fh:
        for name in sorted(owned):
            slug = owned[name]
            for query in QUERIES:
                if (slug, query) in existing:
                    continue
                fh.write("%s|%s\n" % (slug, query))
                added.append((slug, query))
    io.open(os.path.join(HERE, "_no_cover.json"), "w", encoding="utf-8").write(
        json.dumps(no_cover, ensure_ascii=False, indent=1))
    print(json.dumps({"cities_owned": len(owned), "no_cover": len(no_cover),
                      "added_pairs": len(added)}))


if __name__ == "__main__":
    main()
