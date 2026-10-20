# -*- coding: utf-8 -*-
"""Опрос Overpass API — есть ли в OSM таджикистанские салоны связи.

usage: python probe_overpass.py
"""
import io
import json
import sys
import time

import requests

OVERPASS = "https://overpass-api.de/api/interpreter"
MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.opencyclemap.com/?command=interpret",
]

# Охват: все POIs в границах TJ, tag shop=mobile_phone OR имя совпадает с
# оператором OR amenity=telephone_office.
QUERY = u"""[out:json][timeout:180];
area["ISO3166-1"="TJ"][admin_level=2]->.tj;
(
  nwr["shop"="mobile_phone"](area.tj);
  nwr["amenity"="telephone_office"](area.tj);
  nwr["office"="telecommunication"](area.tj);
  nwr["name"~"Tcell|Тсел|МегаФон|Megafon|MegaFon|Зет|Zet|Бабилон|Babilon|Beeline|Тоҷиктелеком|Tojiktelecom"](area.tj);
);
out center tags;
"""


def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def main():
    last_err = None
    r = None
    # Экспоненциальный backoff на overpass-api.de (6 попыток: 0/30/60/120/180/240 = ~10 мин)
    for attempt in range(6):
        if attempt:
            wait = 30 * attempt
            print("retry in %ds" % wait)
            time.sleep(wait)
        t0 = time.time()
        try:
            r = requests.post(MIRRORS[0], data={"data": QUERY.encode("utf-8")},
                              headers={"User-Agent": "travel-guide/1.0"},
                              timeout=300)
        except requests.RequestException as e:
            last_err = "exc %s" % type(e).__name__
            print("attempt=%d EXC %s" % (attempt, last_err))
            continue
        print("attempt=%d status=%d bytes=%d elapsed=%.1fs" % (attempt, r.status_code, len(r.text), time.time() - t0))
        if r.status_code == 200 and len(r.text) > 500:
            break
        last_err = "http %d len=%d" % (r.status_code, len(r.text))
    if not (r and r.status_code == 200):
        print("FAILED: %s" % last_err)
        return 1
    if r.status_code != 200:
        print(r.text[:800])
        return 1
    d = r.json()
    els = d.get("elements", [])
    print("elements=%d" % len(els))
    from collections import Counter
    types = Counter(e["type"] for e in els)
    print("types:", dict(types))
    shops = Counter((e.get("tags") or {}).get("shop") for e in els)
    print("shop kinds:", a(dict(shops)))
    named = [e for e in els if any(k in ((e.get("tags") or {}).get("name") or "")
                                   for k in ["Tcell", "Тсел", "МегаФон", "Megafon",
                                             "Зет", "Zet", "Бабилон", "Babilon",
                                             "Beeline", "Tojik", "Тоҷиктелеком"])]
    print("named-telecom=%d" % len(named))
    # Cities
    cities = Counter((e.get("tags") or {}).get("addr:city", "?") for e in named)
    print("cities:", a(dict(cities.most_common(15))))
    # save raw
    io.open("osm_telecom.json", "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False))
    print("wrote osm_telecom.json")
    # sample entries
    for e in named[:8]:
        loc = (e.get("lat"), e.get("lon")) if e["type"] == "node" else ((e.get("center") or {}).get("lat"), (e.get("center") or {}).get("lon"))
        print("  ", e["type"], e.get("id"), "|", a((e.get("tags") or {}).get("name")), "|", a((e.get("tags") or {}).get("addr:city")), "|", loc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
