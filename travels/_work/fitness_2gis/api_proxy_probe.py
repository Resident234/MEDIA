# -*- coding: utf-8 -*-
"""Try the site's own catalog-API proxy paths for one firm id (read-only)."""
import json
import re
import urllib.request
import urllib.error

FID = "70000001103044666"
Q = "id=%s&fields=items.id,items.name,items.address,items.phones,items.contacts,items.contact_groups,items.urls,items.work_time&locale=ru_TJ" % FID
CANDS = [
    "https://2gis.tj/_/api/3.0/items/byid?" + Q,
    "https://2gis.tj/_/api/v3/items/byid?" + Q,
    "https://2gis.tj/api/3.0/items/byid?" + Q,
    "https://2gis.tj/3.0/items/byid?" + Q,
    "https://2gis.tj/_/items/byid?" + Q,
    "https://2gis.tj/dushanbe/api/3.0/items/byid?" + Q,
]
HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Referer": "https://2gis.tj/dushanbe/firm/%s" % FID,
    "X-Requested-With": "XMLHttpRequest",
}
for u in CANDS:
    tag = u.replace("https://2gis.tj", "")[:38]
    try:
        req = urllib.request.Request(u, headers=HDRS)
        r = urllib.request.urlopen(req, timeout=25)
        body = r.read().decode("utf-8", "replace")
        is_json = body.lstrip()[:1] in "{["
        hits = len(re.findall(r"\+?992\d|\bphones\b", body))
        print("code=%s len=%d json=%s phone_hits=%d | %s" % (
            r.status, len(body), is_json, hits, tag))
        if is_json and hits:
            print("   " + body[:400].encode("ascii", "backslashreplace").decode("ascii"))
    except urllib.error.HTTPError as e:
        print("HTTP %s len=%s | %s" % (e.code, len(e.read() or b""), tag))
    except Exception as e:
        print("ERR %s | %s" % (type(e).__name__, tag))
