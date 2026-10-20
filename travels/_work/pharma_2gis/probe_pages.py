# -*- coding: utf-8 -*-
"""Проверить, добирается ли SSR-выдача 2ГИС по страницам/плиткам без API.

usage: python probe_pages.py

Из бандлов ключ не извлечён (веб ходит в API через свой бэкенд), поэтому
остаётся один канал — серверная выдача `2gis.tj/<город>/search/<запрос>`.
Она отдаёт 12 карточек из `total`, и надо понять, умеет ли сервер отдавать
дальше:

1. `?page=N` — обычная пагинация;
2. `&_p=N` / `/pageN` — варианты, которые у 2ГИС бывали в SEO-URL;
3. `?center=<lon,lat>&zoom=Z` — выдача, привязанная к видимому экрану: если
   сервер честно реагирует на центр и зум, полный список собирается
   плитками, как это делал collect_deep.py через API;
4. что вообще лежит в состоянии страницы: id карточек, координаты, график
   работы, total, подсказки о числе страниц.

Сравниваются множества id: если они не меняются — канал закрыт и 2GIS-часть
ограничится первой страницей + уже накопленными массивами.
"""
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0"
CITY = "dushanbe"
Q = "аптеки"


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "ru-RU,ru;q=0.8"})
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return resp.getcode(), resp.read().decode("utf-8", "replace")
    except Exception as exc:                       # noqa: BLE001
        return -1, repr(exc)[:160]


def ids_of(t):
    return set(re.findall(r"/%s/(?:firm|carid)/(\d{6,})" % CITY, t))


def main():
    base = "https://2gis.tj/%s/search/%s" % (CITY, urllib.parse.quote(Q.encode("utf-8")))
    variants = [
        ("plain", base),
        ("page2", base + "?page=2"),
        ("page3", base + "?page=3"),
        ("p_param", base + "&_p=2"),
        ("table_view", base + "?view=table&page=2"),
        ("zoom12_city", base + "&center=68.7864,38.5598&zoom=12"),
        ("zoom14_tile1", base + "&center=68.7600,38.5600&zoom=14"),
        ("zoom14_tile2", base + "&center=68.8200,38.5600&zoom=14"),
        ("zoom16_tile", base + "&center=68.7600,38.5600&zoom=16"),
        ("rubric", "https://2gis.tj/%s/rubric/110179" % CITY),
    ]
    prev = None
    out = {}
    for name, url in variants:
        code, t = get(url)
        row = {"code": code, "bytes": len(t), "ids": len(ids_of(t))}
        if code == 200:
            row["total"] = sorted(set(re.findall(r'"total"\s*:\s*(\d+)', t)))[:5]
            new = ids_of(t) - (prev or set())
            row["new_ids_vs_prev"] = len(new)
            row["sample"] = sorted(new)[:4]
            prev = ids_of(t) | (prev or set())
        else:
            row["err"] = ascii_(t[:100])
        out[name] = row
        print("%-13s %s" % (name, ascii_(json.dumps(row, ensure_ascii=True))))
    io.open(os.path.join(HERE, "_pages_probe.json"), "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=True, indent=1))
    # заодно распечатать, какие поля есть у карточки в состоянии страницы
    code, t = get(base)
    m = re.search(r'"items":\s*\[\s*\{.{0,3000}', t, re.S)
    if m:
        blob = m.group(0)
        print("item keys:", ascii_(sorted(set(re.findall(r'"([a-z_]{3,22})"\s*:', blob)))[:60]))
        print("snippet:", ascii_(blob[:900]))


if __name__ == "__main__":
    main()
