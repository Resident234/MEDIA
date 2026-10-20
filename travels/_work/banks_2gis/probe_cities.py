# -*- coding: utf-8 -*-
"""Пробовать домены 2GIS для Худжанда, Бохтара, Куляба и других городов TJ.

usage: python probe_cities.py
"""
import io
import json
import sys
import urllib.parse
import requests

CITIES = ["khujand", "khudzhand", "kulyab", "bokhtar", "khujand-tj", "dushanbe"]
UA = "Mozilla/5.0"

def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")

def probe(city, q=u"банки"):
    url = "https://2gis.tj/%s/search/%s" % (city, urllib.parse.quote(q.encode("utf-8")))
    try:
        r = requests.get(url, headers={"User-Agent": UA},
                         timeout=(15, 60), allow_redirects=True)
        body = r.text
        # detect initialState
        idx = body.find("initialState")
        return {
            "city": city,
            "url_req": url,
            "status": r.status_code,
            "final_url": r.url,
            "len": len(body),
            "has_state": idx > 0,
            "redirected": r.url != url,
        }
    except Exception as e:
        return {"city": city, "err": str(e)[:100]}

def main():
    for c in CITIES:
        info = probe(c)
        print(a(json.dumps(info, ensure_ascii=True)))

if __name__ == "__main__":
    main()
