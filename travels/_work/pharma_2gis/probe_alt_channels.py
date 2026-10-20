# -*- coding: utf-8 -*-
"""Последние запасные каналы 2ГИС: старый API, другие домены, обход по карточкам.

usage: python probe_alt_channels.py

Свежий браузер отдаёт капчу (`captcha.2gis.ru/form`), SSR-выдача ограничена
12 карточками на запрос. Прежде чем признать 2GIS-канал закрытым, проверяется
всё, что ещё теоретически может дать список организаций:

1. `catalog.api.2gis.ru/2.0/` и `catalog.api.2gis.com/3.0/` с тем же ключом —
   блок висит на ключе, но домен/версию это не исключает;
2. `search.2gis.ru`, `2gis.tj/_/search` — служебные пути вебклиента;
3. есть ли в сохранённой SSR-карточке (2016 страниц в shops_2gis/ssr_pages)
   ссылки на другие организации: блоки «рядом», «похожие», список соседних
   филиалов сети. Если да — id аптек обходятся графом от известной карточки,
   и капча с API не нужны;
4. отдаёт ли SSR-карточка часы работы и адрес (наш источник `время работы`
   для раздела 11).

Отчёт ASCII-escaped, складывается в _alt_channels.json.
"""
import glob
import io
import json
import os
import re
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SHOPS = os.path.join(HERE, "..", "shops_2gis")
KEY = os.environ.get("TWOGIS_API_KEY", "b82d3fc7-0219-43a3-86a2-d5baaef7a6be")
UA = "Mozilla/5.0"


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        resp = urllib.request.urlopen(req, timeout=40)
        return resp.getcode(), resp.read().decode("utf-8", "replace")
    except Exception as exc:                       # noqa: BLE001
        return -1, repr(exc)[:180]


def main():
    out = {}
    q = urllib.parse.quote("аптека".encode("utf-8"))
    city = "70030076174471798"
    print("=== api variants ===")
    urls = [
        ("2.0_items", "https://catalog.api.2gis.ru/2.0/items?q=%s&city_id=%s&limit=1&key=%s" % (q, city, KEY)),
        ("3.0_items_ru", "https://catalog.api.2gis.ru/3.0/items?q=%s&city_id=%s&limit=1&key=%s" % (q, city, KEY)),
        ("3.0_items_com", "https://catalog.api.2gis.com/3.0/items?q=%s&city_id=%s&limit=1&key=%s" % (q, city, KEY)),
        ("3.0_items_kz", "https://catalog.api.2gis.kz/3.0/items?q=%s&city_id=%s&limit=1&key=%s" % (q, city, KEY)),
        ("3.0_items_tj", "https://catalog.api.2gis.tj/3.0/items?q=%s&city_id=%s&limit=1&key=%s" % (q, city, KEY)),
        ("search2gis", "https://search.2gis.ru/search?q=%s&city_id=%s&key=%s" % (q, city, KEY)),
        ("web_search_path", "https://2gis.tj/_/search?q=%s" % q),
        ("web_items_path", "https://2gis.tj/dushanbe/search/items?q=%s" % q),
    ]
    api = {}
    for name, u in urls:
        code, t = fetch(u)
        head = ascii_(t[:170])
        item = {"code": code, "head": head}
        m = re.search(r'"code"\s*:\s*(\d+)', t)
        if m:
            item["meta_code"] = m.group(1)
        mm = re.search(r'"total"\s*:\s*(\d+)', t)
        if mm:
            item["total"] = mm.group(1)
        api[name] = item
        print("%-15s %s" % (name, ascii_(json.dumps(item, ensure_ascii=True))[:230]))
    out["api"] = api

    print("=== other org links inside SSR cards ===")
    pages = sorted(glob.glob(os.path.join(SHOPS, "ssr_pages", "*.html")))
    print("ssr pages on disk:", len(pages))
    if pages:
        t = io.open(pages[0], encoding="utf-8").read()
        firms = set(re.findall(r"/(?:dushanbe)/(?:firm|carid)/(\d{6,})", t))
        print("other firm ids in one card:", len(firms))
        blocks = re.findall(r'"(?:similar|neighbors|nearby|also_like|related)[a-z_]*"', t, re.I)
        print("hint blocks:", sorted(set(blocks))[:10])
        print("keys near firm links:",
              ascii_(sorted(set(re.findall(r'"([a-z_]{4,22})":\s*\[?\{"id":"7000', t)))[:12]))
        # есть ли в карточке часы и адрес — это то, ради чего канал нужен
        for pat in (r'"schedule"', r'"working_time"', r'"address"', r'"phones"',
                    r'"website"', r'(?i)whatsapp|instagram|telegram'):
            print("  %-24s hits=%d" % (pat, len(re.findall(pat, t))))
        out["card_sample"] = {"file": os.path.basename(pages[0]),
                             "other_firm_ids": len(firms),
                             "hints": sorted(set(blocks))[:10]}
    io.open(os.path.join(HERE, "_alt_channels.json"), "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=True, indent=1))


if __name__ == "__main__":
    main()
