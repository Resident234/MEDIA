# -*- coding: utf-8 -*-
"""Найти ключ и настройки API, с которыми работает собственный веб-клиент 2ГИС.

usage: python probe_site_key.py

Страница выдачи 2gis.tj отдаёт серверный JSON (12 карточек из `total: 118`) и
ссылается на `catalog.api.2gis.ru/3.0/` — значит дальше выдачу добирает
клиентскими запросами к тому же API, но уже с ключом, зашитым в бандле, а не
с нашим заблокированным демо-ключом. Задача — вытащить из JS-бандлов:

1. сам ключ (обычно `key:"<uuid>"` или в конфиге API);
2. базовый адрес и путь (/items, /catalog/items);
3. какие параметры клиент передаёт для страниц/плиток (`page`, `_p`,
   `center`, `zoom`, `waypoints`), чтобы уметь повторять его запросы.

Всё печатается ASCII-escaped: консоль Windows в cp866 падает на кириллице и
на символе телефона в og:title.
"""
import io
import json
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0"


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    except Exception as exc:                       # noqa: BLE001
        return "ERR " + repr(exc)[:200]


def main():
    html_path = None
    for name in sorted(os.listdir(HERE)):
        if name.startswith("_probe_search_") and name.endswith(".html") and \
                os.path.getsize(os.path.join(HERE, name)) > 1000:
            html_path = os.path.join(HERE, name)
    if not html_path:
        sys.exit("no probe html")
    t = io.open(html_path, encoding="utf-8").read()
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', t)
    srcs = [s for s in srcs if "2gis" in s or s.startswith("/")]
    print("script srcs:", len(srcs))
    found = {"keys": {}, "api_paths": {}, "page_params": {}, "hosts": {}}
    for s in srcs:
        url = s if s.startswith("http") else "https://2gis.tj" + s
        body = get(url)
        if body.startswith("ERR"):
            print("  skip", ascii_(url[:80]), body[:80])
            continue
        ks = set(re.findall(r"[\"']key[\"']\s*[:=]\s*[\"']([0-9a-f\-]{20,40})[\"']", body))
        for k in ks:
            found["keys"].setdefault(k, []).append(os.path.basename(url)[:30])
        for p in set(re.findall(r"[\"'](/[a-z_]*(?:items|catalog|search|clusters)[a-z_/]*)[\"']", body)):
            found["api_paths"].setdefault(p, []).append(os.path.basename(url)[:30])
        for h in set(re.findall(r"https?://[a-z0-9.\-]*2gis[a-z.]*(?:\.[a-z]{2,3})?/[a-z0-9/._\-]{0,30}", body)):
            found["hosts"].setdefault(h, []).append(os.path.basename(url)[:30])
        for pp in set(re.findall(r"[\"'](page|_p|pagenum|showMore|per_page|center|zoom|waypoints)[\"']", body)):
            found["page_params"].setdefault(pp, 0)
            found["page_params"][pp] += 1
        print("  scanned", ascii_(os.path.basename(url)[:40]), len(body))
    print(json.dumps({k: (v if k != "keys" else {kk: vv[:2] for kk, vv in v.items()})
                      for k, v in found.items()}, ensure_ascii=True, indent=1)[:6000])


if __name__ == "__main__":
    import sys                                           # noqa: E402
    main()
