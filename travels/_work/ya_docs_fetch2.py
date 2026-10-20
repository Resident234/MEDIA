# -*- coding: utf-8 -*-
"""Second pass: fetch the Yandex pages that explain tariffs, quickstart and free limits."""
import io
import json
import re
import html
import urllib.request

URLS = {
    "geosearch_concept": "https://yandex.ru/dev/commercial/doc/ru/concepts/geosearch",
    "quickstart": "https://yandex.ru/dev/commercial/doc/ru/concepts/quickstart",
    "faq": "https://yandex.ru/dev/commercial/doc/ru/faq",
    "prices_new": "https://yandex.ru/maps-api/prices",
    "tariffs": "https://yandex.ru/maps-api/tariffs",
    "products": "https://yandex.ru/maps-api/products",
    "orgapi_params": "https://yandex.ru/dev/commercial/doc/ru/reference/org-search-request",
    "api_market_catalog": "https://api.market/catalog/yandex-business-catalog",
    "dev_maps_home": "https://yandex.ru/dev/maps/",
}


def strip(raw):
    raw = re.sub(r"(?is)<(script|style|noscript|svg|header|footer)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"[ \t\xa0]+", " ", raw)
    raw = re.sub(r"\n\s*\n+", "\n", raw)
    return raw.strip()


out = {}
for key, url in URLS.items():
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9",
        })
        r = urllib.request.urlopen(req, timeout=25)
        raw = r.read().decode("utf-8", "replace")
        out[key] = {"final": r.geturl(), "code": r.status, "raw": len(raw), "text": strip(raw)}
    except Exception as e:
        out[key] = {"error": str(e)[:200], "url": url}

io.open("ya_docs_dump2.json", "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False))
for k in out:
    v = out[k]
    line = "%-18s %s" % (k, v.get("error", "%s raw=%d text=%d" % (v["code"], v["raw"], len(v["text"]))))
    print(line.encode("ascii", "backslashreplace").decode("ascii")[:120])
