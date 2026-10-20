# -*- coding: utf-8 -*-
"""Server-side probe of 2GIS web cards: does the raw HTML (no browser) carry contacts?"""
import io
import json
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
IDS = ["70000001103044666", "70000001101445485", "70000001101229632"]
HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Connection": "close",
}
PHONE = re.compile(r"\+?\d{1,3}[-\s(]?\d{2,3}[-\s)]?\d{2}[-\s]?\d{2}(?:[-\s]?\d{2})?")

rows = []
for fid in IDS:
    url = "https://2gis.tj/dushanbe/firm/%s" % fid
    rec = {"id": fid, "url": url}
    try:
        req = urllib.request.Request(url, headers=HDRS)
        r = urllib.request.urlopen(req, timeout=30)
        body = r.read().decode("utf-8", "replace")
        rec["code"] = int(r.status)
        rec["final"] = r.geturl()
        rec["len"] = len(body)
        io.open(os.path.join(HERE, "html_%s.html" % fid), "w", encoding="utf-8").write(body)
        rec["has_captcha"] = bool(re.search(r"captcha", body, re.I))
        rec["tel_links"] = len(re.findall(r"tel:", body, re.I))
        rec["wa"] = len(re.findall(r"wa\.me|whatsapp", body, re.I))
        rec["tg"] = len(re.findall(r"t\.me|telegram", body, re.I))
        rec["phones_kw"] = len(re.findall(r"phones|contact", body, re.I))
        rec["plus992"] = len(re.findall(r"\+992|992\d{2}", body))
        rec["phone_hits"] = PHONE.findall(body)[:8]
        rec["scripts"] = re.findall(r'src="([^"]{0,120}\.js[^"]*)"', body)[:5]
    except Exception as exc:
        rec["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:160])
    rows.append(rec)

io.open(os.path.join(HERE, "html_probe.json"), "w", encoding="utf-8").write(
    json.dumps(rows, ensure_ascii=False, indent=1))
for r in rows:
    line = "%s code=%s len=%s captcha=%s tel=%d wa=%d tg=%d phones_kw=%d plus992=%d err=%s" % (
        r["id"][-6:], r.get("code"), r.get("len"), r.get("has_captcha"),
        r.get("tel_links", -1), r.get("wa", -1), r.get("tg", -1),
        r.get("phones_kw", -1), r.get("plus992", -1), r.get("error", "")[:70])
    print(line.encode("ascii", "backslashreplace").decode("ascii"))
    print("   hits %s" % json.dumps(r.get("phone_hits", []))[:120])
    print("   js   %s" % json.dumps(r.get("scripts", []))[:200])
