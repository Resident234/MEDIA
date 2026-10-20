# -*- coding: utf-8 -*-
"""Third pass: keys page, free limits, API Market business catalog."""
import io
import json
import re
import html
import urllib.request

URLS = {
    "console_keys": "https://yandex.ru/maps-api/console/keys",
    "jsapi_limits": "https://yandex.ru/dev/maps/jsapi/doc/concepts/limits.html",
    "jsapi_getkey": "https://yandex.ru/dev/maps/jsapi/doc/concepts/get-api-key.html",
    "geocoder_about": "https://yandex.ru/dev/maps/geocoder/doc/dg/concepts/about.html",
    "commercial_about": "https://yandex.ru/dev/maps/commercial/doc/concepts/about.html",
    "apimarket_cat": "https://api.market/catalog/478913",
    "apimarket_main": "https://api.market/",
    "maps_api_home": "https://yandex.ru/maps-api/",
}


def strip(raw):
    raw = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw)
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
        out[key] = {"final": r.geturl(), "code": int(r.status), "raw": len(raw), "text": strip(raw)}
    except Exception as exc:
        out[key] = {"error": type(exc).__name__ + ": " + str(exc)[:160], "url": url}

io.open("ya_docs_dump3.json", "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False))
report = []
for k in URLS:
    v = out.get(k, {})
    if "error" in v:
        report.append("%-17s ERR %s" % (k, v["error"][:110]))
    else:
        report.append("%-17s %s text=%d | %s" % (k, v["code"], len(v["text"]), v["final"][:90]))
io.open("ya_fetch_report.txt", "w", encoding="utf-8").write("\n".join(report))
print("\n".join(report).encode("ascii", "backslashreplace").decode("ascii"))
