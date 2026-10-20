# -*- coding: utf-8 -*-
"""Разобрать серверный JSON выдачи 2ГИС, лежащий в HTML страницы поиска.

usage: python probe_state.py <файл.html>

Нужно понять три вещи, от них зависит весь план 2GIS-части:
1. в каком виде внутри HTML лежат карточки (плоский JSON, экранированный
   внутри строки, фрагментами) и какие поля у них есть — id, название,
   адрес, координаты, рейтинг, график;
2. видит ли сервер total (сколько всего аптек в городе) и n-ю страницу, или
   SSR отдаёт только первую страницу;
3. можно ли по этим id дальше идти знакомым SSR-каналом карточки
   (https://2gis.tj/dushanbe/firm/<id>), который уже работает без API.
"""
import glob
import io
import json
import os
import re
import sys

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        # кириллица в аргументах PowerShell искажается, поэтому файл ищем сами
        cands = [p for p in sorted(glob.glob(os.path.join(here, "_probe_search_*.html")))
                 if os.path.getsize(p) > 1000]
        if not cands:
            sys.exit("no probe html files")
        path = cands[-1]
    print("file", os.path.basename(path).encode("ascii", "backslashreplace").decode())
    t = io.open(path, encoding="utf-8").read()
    print("bytes", len(t))
    # где вообще начинается состояние: ищем маркеры и берём окружение
    for marker in ("items\":[", "\"total\":", "\"point\":", "\"geometry\":"):
        idx = t.find(marker)
        print("marker %-14s first at %d" % (marker, idx))
    m = re.search(r'"total"\s*:\s*(\d+)', t)
    print("total values:", sorted(set(re.findall(r'"total"\s*:\s*(\d+)', t)))[:10])
    print("per_page items keys sample:")
    # соберём все id с названиями рядом
    blocks = re.findall(r'\{"id":"(\d{10,})"(.{0,600})', t)
    print(" id-prefixed blocks:", len(blocks))
    for bid, tail in blocks[:3]:
        keys = re.findall(r'"([a-z_]{3,20})":', tail)
        print("  ", bid, sorted(set(keys))[:25])
    print("address_name hits:", len(re.findall(r'"address_name"', t)))
    print("point/lon hits:", len(re.findall(r'"point"\s*:\s*\[', t)),
          len(re.findall(r'"lon"', t)))
    print("rating hits:", len(re.findall(r'"rating"', t)))
    print("working_time hits:", len(re.findall(r'(?i)working_(?:time|hours)|business_hours', t)))
    print("phones hits:", len(re.findall(r'"phones"\s*:\s*\[', t)))
    # try to locate a big JSON blob and parse it
    m2 = re.search(r'window\.__\w+\s*=\s*', t)
    print("state assignment:", m2.group(0)[:60] if m2 else None)
    for cand in re.findall(r'window\.(\w+)\s*=', t):
        print("  window var:", cand)
    print("urls with page param:", sorted(set(re.findall(r'[?&]page=(\d+)', t)))[:8])
    print("seo canonical:", re.findall(r'<link rel="canonical" href="([^"]+)"', t)[:2])
    print("og:title:", re.findall(r'property="og:title" content="([^"]{0,120})"', t)[:2])

if __name__ == "__main__":
    main()
