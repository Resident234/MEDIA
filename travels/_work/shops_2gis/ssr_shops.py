# -*- coding: utf-8 -*-
"""SSR-crawl the collected 2GIS cards and pull contacts / соцсети / приложения.

Same channel as fitness_2gis/ssr_crawl.py: 2gis.tj returns the full server
HTML of a card only for the bare User-Agent "Mozilla/5.0" (a full Chrome UA
gets a 11-КБ JS shell, a real cookieless browser gets captcha). Values are
read strictly from the card's own state container ("«id»":{"data":{...}}")
so phones/links from the "похожие организации" block never stick to a wrong
row.

Unlike the fitness pass this one also collects:
  * every contact type (phone/website/email/social/viber/whatsapp/telegram…),
  * app links — App Store / Google Play / RuStore / AppGallery URLs are
    searched inside the card container only (the request asks for them and
    they are the rarest field on a card).

To keep ~2000 pages off the disk, raw HTML is written to ssr_pages/ only for
cards whose container failed to parse (the rest is re-downloadable); the
resume ledger is ssr_cards.jsonl itself (append + skip-by-id).

usage: python ssr_shops.py [limit] [start]
"""
import io
import json
import os
import re
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0"
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
PAGES = os.path.join(HERE, "ssr_pages")
OUT = os.path.join(HERE, "ssr_cards.jsonl")
REPORT = os.path.join(HERE, "ssr_report.json")
PAUSE = 2.5
APP_RE = re.compile(
    r'https?://(?:[^\s"]*?(?:apps\.apple\.com|play\.google\.com|'
    r'[a-z.]*rustore\.ru|appgallery\.huawei\.com|[^\s"]*appstar\.ru|'
    r'store\.mygames\.ru|download\.android\.com)[^\s"]*)')
DAY_RU = {"Mon": "пн", "Tue": "вт", "Wed": "ср", "Thu": "чт", "Fri": "пт",
          "Sat": "сб", "Sun": "вс"}
ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def fmt_schedule(schedule):
    if not isinstance(schedule, dict) or not schedule:
        return None
    days = []
    for d in ORDER:
        if d not in schedule:
            continue
        wh = schedule[d].get("working_hours") or []
        hours = ", ".join("%s–%s" % (h.get("from", "?"), h.get("to", "?")) for h in wh)
        days.append((DAY_RU[d], hours or "?"))
    if not days:
        return None
    runs = []
    for name, h in days:
        if runs and runs[-1][1] == h:
            runs[-1][0].append(name)
        else:
            runs.append(([name], h))
    parts = []
    for names, h in runs:
        parts.append(("%s–%s" % (names[0], names[-1]) if len(names) > 1 else names[0]) + " " + h)
    return "; ".join(parts)


def extract_container(body, item_id):
    marker = '"%s":{"data":{' % item_id
    i = body.find(marker)
    if i < 0:
        return None, None
    start = i + len(marker) - len('{"data":{')
    try:
        obj, end = json.JSONDecoder().raw_decode(body, start)
        return obj, json.dumps(obj, ensure_ascii=True).replace("\\/", "/")
    except ValueError:
        return None, None


def parse_card(body, item_id):
    rec = {"id": item_id}
    cont, cont_json = extract_container(body, item_id)
    rec["container_found"] = cont is not None
    if not cont:
        return rec
    data = cont.get("data", {})
    rec["ssr_name"] = data.get("name")
    rec["updated_at"] = (data.get("dates") or {}).get("updated_at")
    rec["schedule"] = fmt_schedule(data.get("schedule"))
    contacts = []
    for grp in data.get("contact_groups") or []:
        for c in grp.get("contacts") or []:
            contacts.append({k: c.get(k) for k in ("type", "text", "value", "url")
                             if c.get(k) is not None})
    rec["contacts"] = contacts
    # приложение: только из контейнера карточки
    rec["apps"] = sorted(set(APP_RE.findall(cont_json or "")))
    return rec


def fetch(url, path):
    last = None
    for attempt in (1, 2, 3):
        try:
            r = SESSION.get(url, timeout=(15, 75))
            body = r.text
            if r.status_code == 200 and len(body) > 50000 and "captcha" not in r.url:
                return "fresh", body
            last = "blocked(len=%d,code=%d,url=%s)" % (len(body), r.status_code, r.url)
        except requests.RequestException as e:
            last = "error(%s)" % type(e).__name__
        time.sleep(3 + attempt * 2)
    return last, ""


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10 ** 9
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    targets = json.load(io.open(os.path.join(HERE, "web_targets.json"), encoding="utf-8"))
    done = set()
    if os.path.exists(OUT):
        for line in io.open(OUT, encoding="utf-8"):
            try:
                rec = json.loads(line)
                if rec.get("ok"):
                    done.add(rec["id"])
            except ValueError:
                pass
    os.makedirs(PAGES, exist_ok=True)
    fh = io.open(OUT, "a", encoding="utf-8", newline="\n")
    stats = {"ok": len(done), "skipped": 0, "blocked": 0, "bad": 0}
    worked = 0
    for i, t in enumerate(targets[start:], start + 1):
        if t["id"] in done:
            stats["skipped"] += 1
            continue
        src, body = fetch(t["url"], None)
        if src != "fresh":
            rec = {"id": t["id"], "ok": False, "error": src}
            stats["blocked"] += 1
        else:
            rec = parse_card(body, t["id"])
            rec["ok"] = bool(rec.get("container_found"))
            if rec["ok"]:
                stats["ok"] += 1
            else:
                # оставить след только для разбора провала
                io.open(os.path.join(PAGES, t["id"] + ".html"), "w",
                        encoding="utf-8").write(body)
                stats["bad"] += 1
            del body
        rec["name"] = t["name"]
        rec["key"] = t.get("key")
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        worked += 1
        if worked % 20 == 0:
            print("[%04d] ok=%d blocked=%d bad=%d last=%s" % (
                i, stats["ok"], stats["blocked"], stats["bad"],
                json.dumps(t["id"], ensure_ascii=True)), flush=True)
        time.sleep(PAUSE)
        if worked >= limit:
            break
    fh.close()
    io.open(REPORT, "w", encoding="utf-8").write(
        json.dumps(stats, ensure_ascii=False, indent=1))
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
