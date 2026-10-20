# -*- coding: utf-8 -*-
"""Overpass API: банки в Худжанде (bbox).

usage: python probe_khj.py

bbox для Худжанда: (south=40.15, west=69.45, north=40.55, east=69.90).
Канал: amenity=bank OR amenity=bureau_de_change (обмен валют). Без ATM —
нам нужны отделения/офисы, а не уличные банкоматы.
"""
import io
import json
import sys
import time
import requests

MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

QUERY = u"""[out:json][timeout:120];
(
  nwr["amenity"="bank"](40.15,69.45,40.55,69.90);
  nwr["amenity"="bureau_de_change"](40.15,69.45,40.55,69.90);
);
out center tags;
"""


def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def main():
    last_err = None
    r = None
    for attempt in range(6):
        if attempt:
            wait = 20 * attempt
            print("retry in %ds" % wait)
            time.sleep(wait)
        t0 = time.time()
        try:
            r = requests.post(MIRRORS[0], data={"data": QUERY.encode("utf-8")},
                              headers={"User-Agent": "travel-guide/1.0"},
                              timeout=180)
        except requests.RequestException as e:
            last_err = "exc %s" % type(e).__name__
            print("attempt=%d EXC %s" % (attempt, last_err))
            continue
        print("attempt=%d status=%d bytes=%d elapsed=%.1fs" % (
            attempt, r.status_code, len(r.text), time.time() - t0))
        if r.status_code == 200 and len(r.text) > 100:
            break
        last_err = "http %d len=%d" % (r.status_code, len(r.text))
    if not (r and r.status_code == 200):
        print("FAILED: %s" % last_err)
        return 1
    d = r.json()
    els = d.get("elements", [])
    print("elements=%d" % len(els))
    io.open("osm_khj_banks.json", "w", encoding="utf-8").write(
        json.dumps(d, ensure_ascii=False))
    print("wrote osm_khj_banks.json")
    named = [e for e in els if (e.get("tags") or {}).get("name")]
    print("named=%d" % len(named))
    for e in named[:15]:
        loc = (e.get("lat"), e.get("lon")) if e["type"] == "node" else (
            (e.get("center") or {}).get("lat"),
            (e.get("center") or {}).get("lon"))
        t = e.get("tags") or {}
        print("  ", e["type"], e.get("id"), "|", a(t.get("name")),
              "|", a(t.get("addr:street")), "|", t.get("contact:phone"),
              "|", loc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
