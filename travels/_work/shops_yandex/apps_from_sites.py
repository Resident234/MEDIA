# -*- coding: utf-8 -*-
"""Collect application links from the organisations' OWN websites.

usage: python apps_from_sites.py [limit]

The request asks for «ссылки на приложение». Map services barely publish an
app field for Tajik shops: no app-store link has shown up in the whole 2GIS
web-card crawl (ssr_cards.jsonl), and the Yandex card template keeps apps
under a button the crawler cannot open. The one honest source left is the
organisation's own site — a link there is published by the organisation
itself, exactly like the phone number in the card.

So: take the website each 2GIS card declares (the human-readable domain from
the contact text, not the link.2gis.ru redirect), fetch the homepage once per
DISTINCT domain, and pull app-store links out of the HTML. Anything matching
an app store that is NOT on the org's own domain is still kept but marked
foreign, so the aggregation can refuse it. Results go to apps_sites.json
{domain: {"apps": [...], "checked": ..., "status": ...}}; already-checked
domains are skipped, so the run is resumable.

No name-based app-store search is used here on purpose: probing the public
iTunes lookup endpoint with shop names returned e.g. a Moroccan Auchan build
and a Pakistani grocery app for «Ашан»/«Баракат» — attaching those to Tajik
cards would be fabrication, not data.
"""
import io
import json
import os
import re
import sys
import time
from urllib.parse import urlparse

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "apps_sites.json")
LEDGER = os.path.join(HERE, "..", "shops_2gis", "ssr_cards.jsonl")
UA = "Mozilla/5.0"
PAUSE = 1.2
APP_RE = re.compile(
    r"https?://(?:apps\.apple\.com|[A-Za-z0-9.-]*\.appstore\.com|"
    r"play\.google\.com|rustore\.ru|appgallery\.huawei\.com|appstar\.ru|"
    r"store\.mygames\.ru|download\.android\.com|"
    r"a\.appsflyer\.com|onel\.ink|qr\.app\b)[^\s\"'<>)]*", re.I)
STORE_HOSTS = ("apps.apple.com", "play.google.com", "rustore.ru",
               "appgallery.huawei.com", "appstar.ru", "store.mygames.ru",
               "download.android.com")


def clean_link(link):
    """HTML entities and escaping artefacts off an app-store URL."""
    import html as _html
    link = _html.unescape(link or "")
    link = link.replace("\\/", "/").rstrip("\\")
    return link.strip()


def domains():
    """domain -> [card ids] from the website contacts of the SSR ledger."""
    table = {}
    if not os.path.exists(LEDGER):
        return table
    for line in io.open(LEDGER, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not rec.get("ok"):
            continue
        for c in rec.get("contacts") or []:
            if (c.get("type") or "").lower() != "website":
                continue
            text = (c.get("text") or "").strip()
            url = (c.get("url") or c.get("value") or "")
            real = ""
            m = re.search(r"\?(https?://.+)$", url)
            if m:
                real = m.group(1)
            host = urlparse(real or ("http://" + text)).netloc.lower()
            host = re.sub(r"^www\.", "", host)
            if not host or host.endswith("2gis.ru") or host.endswith("2gis.tj"):
                continue
            table.setdefault(host, []).append(rec["id"])
    return table


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    table = domains()
    done = {}
    if os.path.exists(OUT):
        done = json.load(io.open(OUT, encoding="utf-8"))
    print(json.dumps({"domains": len(table), "already": len(done)},
                     ensure_ascii=True), flush=True)
    worked = 0
    for host, ids in sorted(table.items(), key=lambda kv: -len(kv[1])):
        if host in done:
            continue
        rec = {"cards": len(ids), "checked": time.strftime("%Y-%m-%d %H:%M")}
        base = host if "://" in host else host
        # https first, then plain http — many Tajik sites answer 404/50x on the
        # wrong scheme rather than redirecting.
        cand = ["https://" + base, "http://" + base]
        r = None
        errs = []
        for url in cand:
            try:
                resp = requests.get(url, timeout=25, headers={"User-Agent": UA},
                                    allow_redirects=True)
            except requests.RequestException as exc:
                errs.append(str(exc)[:120])
                continue
            if r is None or resp.status_code < 400:
                r = resp
            if resp.status_code < 400:
                break
        found = []
        if r is not None:
            rec["status"] = r.status_code
            rec["final"] = r.url
            for m in APP_RE.finditer(r.text or ""):
                link = clean_link(m.group(0))
                if link and link not in found:
                    found.append(link)
        else:
            rec["status"] = "error"
            rec["error"] = " | ".join(errs)[:200]
        rec["apps"] = found[:6]
        rec["own"] = [a for a in found[:6] if any(h in a for h in STORE_HOSTS)]
        done[host] = rec
        with io.open(OUT, "w", encoding="utf-8") as fh:
            json.dump(done, fh, ensure_ascii=False, indent=1)
        print("%-28s %s apps=%d" % (json.dumps(host, ensure_ascii=True)[:28],
                                    rec.get("status"), len(rec.get("apps") or [])),
              flush=True)
        worked += 1
        if limit and worked >= limit:
            break
        time.sleep(PAUSE)
    hits = {k: v for k, v in done.items() if v.get("apps")}
    print(json.dumps({"domains_checked": len(done), "with_apps": len(hits),
                      "hits": {json.dumps(k, ensure_ascii=True): v["apps"]
                               for k, v in list(hits.items())[:40]}},
                     ensure_ascii=True)[:3000], flush=True)


if __name__ == "__main__":
    main()
