# -*- coding: utf-8 -*-
"""Фаза 2 для лабораторий: карточки 2ГИС по id из rows.jsonl.

usage:
  python ssr_cards.py              # сколько успели, столько и сняли
  python ssr_cards.py 200          # лимит запусков за раз
  python ssr_cards.py --retest     # добирает ok=False

Канал: `https://2gis.tj/dushanbe/firm/<id>/` под UA `Mozilla/5.0` — только
с ним сервер отдаёт полный HTML со state, где есть `contact_groups`
(телефоны, сайты, соцсети, мессенджеры) и `schedule`. Тот же приём, что в
pharma_2gis/ssr_cards.py.

Из seed_by_shops сознательно убран фильтр «только аптеки» — для лабораторий
по прошлой съёмке покупок полезного нет, почти все id придётся качать
заново.
"""
import io
import json
import os
import re
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = os.path.join(HERE, "rows.jsonl")
OUT = os.path.join(HERE, "card.jsonl")
LOG = os.path.join(HERE, "card.log")
PAGES = os.path.join(HERE, "card_pages")
UA = "Mozilla/5.0"
HEADERS = {"User-Agent": UA,
           "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
PAUSE = 2.5
CITY = "dushanbe"
APP_RE = re.compile(
    r'https?://(?:[^\s"]*?(?:apps\.apple\.com|play\.google\.com|'
    r'[a-z.]*rustore\.ru|appgallery\.huawei\.com|[^\s"]*appstar\.ru|'
    r'store\.mygames\.ru|download\.android\.com)[^\s"]*)')
DAY_RU = {"Mon": u"пн", "Tue": u"вт", "Wed": u"ср", "Thu": u"чт",
          "Fri": u"пт", "Sat": u"сб", "Sun": u"вс"}
ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def fmt_schedule(schedule):
    if not isinstance(schedule, dict) or not schedule:
        return None
    days = []
    for d in ORDER:
        v = schedule.get(d)
        if not isinstance(v, dict):
            continue
        wh = v.get("working_hours") or []
        hours = ", ".join(u"%s\u2013%s" % (h.get("from", "?"), h.get("to", "?"))
                          for h in wh if isinstance(h, dict))
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
        label = (u"%s\u2013%s" % (names[0], names[-1])) if len(names) > 1 else names[0]
        parts.append(label + " " + h)
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
    data = (cont or {}).get("data", {}) or {}
    rec["ssr_name"] = data.get("name")
    rec["updated_at"] = (data.get("dates") or {}).get("updated_at")
    sch = data.get("schedule") or {}
    rec["is_24x7"] = bool(sch.get("is_24x7")) if isinstance(sch, dict) else False
    rec["schedule"] = fmt_schedule(sch)
    contacts = []
    for grp in data.get("contact_groups") or []:
        for c in grp.get("contacts") or []:
            contacts.append({k: c.get(k) for k in
                             ("type", "text", "value", "url", "caption")
                             if c.get(k) is not None})
    rec["contacts"] = contacts
    rec["apps"] = sorted(set(APP_RE.findall(cont_json or "")))
    org = data.get("org") or {}
    rec["org_name"] = org.get("name") or org.get("primary")
    # Для лабораторий полезен адрес из карточки (иногда в rows его нет).
    addr = data.get("address") or {}
    if isinstance(addr, dict):
        rec["address_name"] = addr.get("unified") or addr.get("value")
    return rec


def fetch(url):
    last = None
    for attempt in (1, 2, 3):
        try:
            r = SESSION.get(url, timeout=(15, 75))
            body = r.text
            if r.status_code == 200 and len(body) > 50000 and "captcha" not in r.url:
                return "fresh", body
            last = "blocked(len=%d,code=%d,url=%s)" % (
                len(body), r.status_code, r.url)
        except requests.RequestException as e:
            last = "error(%s)" % type(e).__name__
        time.sleep(3 + attempt * 2)
    return last, ""


def done_ids(retest=False):
    out = set()
    if not os.path.exists(OUT):
        return out
    for line in io.open(OUT, encoding="utf-8"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("ok") or not retest:
            out.add(str(rec.get("id")))
    return out


def targets():
    ids = []
    seen = set()
    if not os.path.exists(ROWS):
        return ids
    for line in io.open(ROWS, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        i = str(r.get("id"))
        if not i or i in seen:
            continue
        seen.add(i)
        ids.append((i, r.get("name")))
    return ids


def log(msg):
    line = "[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    sys.stdout.write(a(line))
    sys.stdout.flush()
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(line)


def main():
    retest = "--retest" in sys.argv
    limit = None
    for arg in sys.argv[1:]:
        if arg.isdigit():
            limit = int(arg)
            break
    done = done_ids(retest=retest)
    ts = targets()
    log("start: targets=%d done=%d" % (len(ts), len(done)))
    os.makedirs(PAGES, exist_ok=True)
    fh = io.open(OUT, "a", encoding="utf-8", newline="\n")
    stats = {"ok": 0, "blocked": 0, "bad": 0, "skipped": 0}
    worked = 0
    for i, (iid, nm) in enumerate(ts, 1):
        if iid in done:
            stats["skipped"] += 1
            continue
        url = "https://2gis.tj/%s/firm/%s" % (CITY, iid)
        src, body = fetch(url)
        if src != "fresh":
            rec = {"id": iid, "ok": False, "error": src, "name": nm}
            stats["blocked"] += 1
        else:
            rec = parse_card(body, iid)
            rec["ok"] = bool(rec.get("container_found"))
            rec["name"] = nm
            if rec["ok"]:
                stats["ok"] += 1
            else:
                io.open(os.path.join(PAGES, iid + ".html"), "w",
                        encoding="utf-8").write(body)
                stats["bad"] += 1
            del body
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        worked += 1
        if worked % 20 == 0:
            log("[%04d] ok=%d blocked=%d bad=%d last=%s" % (
                i, stats["ok"], stats["blocked"], stats["bad"], iid))
        time.sleep(PAUSE)
        if limit and worked >= limit:
            break
    fh.close()
    log("finish: %s" % json.dumps(stats, ensure_ascii=True))


if __name__ == "__main__":
    main()
