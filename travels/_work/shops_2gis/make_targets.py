# -*- coding: utf-8 -*-
"""Build the SSR crawl target list from items_all.json.

Order matters: the crawl is long (~2000 cards), so the categories the
request names first (базары/рынки/ярмарки, ТЦ, супер-/гипермаркеты, ПВЗ,
интернет-магазины, маркетплейсы, ремёсла/сувениры) are put at the head of
web_targets.json; a partial crawl is then still a partial answer to them.

usage: python make_targets.py
"""
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
KEY_RUBRICS = {"350", "12127", "112611", "110333", "510"}
KEY_QUERIES = {"базар", "бозор", "рынок", "торговый центр", "супермаркет",
               "гипермаркет", "пункт выдачи", "интернет-магазин",
               "маркетплейс", "ремесла", "сувениры", "ярмарка"}


def main():
    rows = json.load(io.open(os.path.join(HERE, "items_all.json"), encoding="utf-8"))
    head, tail = [], []
    for r in rows:
        words = {p.split(":", 1)[1] for p in r["passes"] if p.startswith("query:")}
        is_key = (bool(KEY_RUBRICS & set(r["rubric_ids"]))) or bool(KEY_QUERIES & words)
        (head if is_key else tail).append(r)
    targets = [{"id": r["id"], "name": r["name"], "rating": r["rating"],
                "url": r["url_2gis"], "key": i < len(head)}
               for i, r in enumerate(head + tail)]
    with io.open(os.path.join(HERE, "web_targets.json"), "w", encoding="utf-8") as fh:
        json.dump(targets, fh, ensure_ascii=False, indent=1)
    print(json.dumps({"total": len(targets), "key_first": len(head),
                      "tail_rest": len(tail)}))


if __name__ == "__main__":
    main()
