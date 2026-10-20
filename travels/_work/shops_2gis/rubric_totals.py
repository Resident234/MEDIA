# -*- coding: utf-8 -*-
"""Declared totals for the five rubric passes, which collect_deep.py lost.

usage: python rubric_totals.py   -> rubric_totals.json

`collect_deep.py` asks the rubric total from a separate one-item request, and
in that run every such request came back empty — the report shows
`declared_total: null` for all five rubrics while the tile passes under them
did return cards. The number is worth having, because it is the only evidence
of how much a rubric holds beyond what the tiles could reach. One request per
rubric, `page_size=1`, city_id scope — the same shape the collector used.

Прогон 20.10.2026: тоталы не получены — демо-ключ к этому моменту заблокирован
самим 2ГИС (`403 apiKeyIsBlocked`, «key is blocked, please contact api@2gis.ru»)
после ~551 обращений сбора и ~2000 страниц карточек. Файл `rubric_totals.json`
остаётся с этими `null` — как свидетельство, что цифры нет, а не что её не
искали.
"""
import io
import json
import os
import time

import requests

KEY = os.environ["TWOGIS_API_KEY"]
HERE = os.path.dirname(os.path.abspath(__file__))
ITEMS = "https://catalog.api.2gis.com/3.0/items"
CITY_ID = "70030076174471798"
RUBRICS = {"350": "Супермаркетҳо", "12127": "Гипермаркетҳо",
           "112611": "Нуқтаи додани фармоиши интернетӣ (ПВЗ)",
           "110333": "Молҳои миллӣ", "510": "Тӯҳфаҳо"}


def main():
    out = {}
    for rid, title in RUBRICS.items():
        for attempt in range(3):
            try:
                data = requests.get(ITEMS, params={"rubric_id": rid,
                                                   "city_id": CITY_ID,
                                                   "page_size": 1, "fields": "",
                                                   "key": KEY}, timeout=60).json()
            except (requests.RequestException, ValueError):
                time.sleep(3 + 3 * attempt)
                continue
            code = (data.get("meta") or {}).get("code")
            if code in (429, 408):
                time.sleep(15 + 15 * attempt)
                continue
            out[rid] = {"title": title,
                        "total": (data.get("result") or {}).get("total"),
                        "code": code}
            break
        time.sleep(0.4)
    with io.open(os.path.join(HERE, "rubric_totals.json"), "w",
                 encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=True))


if __name__ == "__main__":
    main()
