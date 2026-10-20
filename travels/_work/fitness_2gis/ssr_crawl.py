# -*- coding: utf-8 -*-
"""Crawl the 19 2GIS web cards via SSR (bare Mozilla/5.0 UA) and pull contacts.

Ключевое наблюдение: 2gis.tj отдаёт полную SSR-страницу карточки (~600 КБ)
только при «голом» User-Agent «Mozilla/5.0»; полный Chrome-UA получает
11-КБ JS-оболочку, а браузер без куки — редирект на captcha.2gis.ru.

Данные извлекаются строго из контейнера карточки в состоянии страницы
(паттерн "«{id}»:{"data":{...}}"), чтобы телефон из рекламных блоков
или подвала 2ГИС не прилип к чужой карточке.

Usage:  python ssr_crawl.py [limit]
Cache:  ssr_pages/{id}.html (повторный запуск докачивает только недостающее)
Output: ssr_cards.jsonl (по одной записи на карточку), ssr_report.json
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
DAY_RU = {"Mon": "пн", "Tue": "вт", "Wed": "ср", "Thu": "чт", "Fri": "пт", "Sat": "сб", "Sun": "вс"}
ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def fmt_schedule(schedule):
    """Сжать расписание вида {Mon:{working_hours:[{from,to}]},...} в компактную строку."""
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
    # сгруппировать одинаковые часы подряд идущих дней
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
    """Достать JSON-контейнер карточки из состояния страницы."""
    marker = '"%s":{"data":{' % item_id
    i = body.find(marker)
    if i < 0:
        return None
    start = i + len(marker) - len('{"data":{')  # на открывающую {
    try:
        obj, _ = json.JSONDecoder().raw_decode(body, start)
        return obj
    except ValueError:
        return None


def parse_card(body, item_id):
    rec = {"id": item_id}
    # отрендеренные телефоны (контрольная сумма для сверки с JSON)
    rec["rendered_tel"] = sorted(set(re.findall(r'href="(tel:\+992[0-9]+)"', body)))
    cont = extract_container(body, item_id)
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
            c2 = {k: c.get(k) for k in ("type", "text", "value", "url") if c.get(k) is not None}
            contacts.append(c2)
    rec["contacts"] = contacts
    rec["phones"] = [c for c in contacts if c.get("type") == "phone"]
    rec["has_whatsapp"] = any("whatsapp" in json.dumps(c).lower() for c in contacts)
    rec["has_telegram"] = any("telegram" in json.dumps(c).lower() for c in contacts)
    # атрибуты карточки (иногда там прячется признак WhatsApp)
    attrs = []
    for ag in data.get("attribute_groups") or []:
        for a in (ag.get("attributes") or []):
            name = a.get("name") or a.get("tag")
            if name:
                attrs.append(name)
    rec["attributes"] = attrs[:20]
    return rec


SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def fetch(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 50000:
        return "cache", io.open(path, encoding="utf-8").read()
    last = None
    for attempt in (1, 2, 3):
        try:
            r = SESSION.get(url, timeout=(15, 75))
            body = r.text
            if r.status_code == 200 and len(body) > 50000 and "captcha" not in r.url:
                io.open(path, "w", encoding="utf-8").write(body)
                return "fresh", body
            last = "blocked(len=%d,code=%d,url=%s)" % (len(body), r.status_code, r.url)
        except requests.RequestException as e:
            last = "error(%s)" % type(e).__name__
        time.sleep(3 + attempt * 2)
    return last, ""


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 99
    targets = json.load(io.open(os.path.join(HERE, "web_targets.json"), encoding="utf-8"))[:limit]
    os.makedirs(PAGES, exist_ok=True)
    done = {}
    if os.path.exists(OUT):
        for line in io.open(OUT, encoding="utf-8"):
            try:
                rec = json.loads(line)
                if rec.get("ok"):
                    done[rec["id"]] = rec
            except Exception:
                pass
    fh = io.open(OUT, "w", encoding="utf-8")
    stats = {"total": len(targets), "ok": 0, "with_phone": 0, "with_hours": 0,
             "with_website": 0, "whatsapp": 0, "telegram": 0, "blocked": 0}
    for i, t in enumerate(targets):
        rec = done.get(t["id"])
        src = "cache"
        if not rec:
            src, body = fetch(t["url"], os.path.join(PAGES, t["id"] + ".html"))
            if src.startswith("blocked"):
                rec = {"id": t["id"], "ok": False, "error": src}
                stats["blocked"] += 1
            else:
                rec = parse_card(body, t["id"])
                rec["ok"] = bool(rec.get("container_found"))
            time.sleep(PAUSE)
        rec["name"] = t["name"]
        rec["rating"] = t["rating"]
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        if rec.get("ok"):
            stats["ok"] += 1
            if rec.get("phones"):
                stats["with_phone"] += 1
            if rec.get("schedule"):
                stats["with_hours"] += 1
            if any(c.get("type") == "website" for c in rec.get("contacts", [])):
                stats["with_website"] += 1
            if rec.get("has_whatsapp"):
                stats["whatsapp"] += 1
            if rec.get("has_telegram"):
                stats["telegram"] += 1
        print("[%02d] %s src=%s ok=%s tel=%s site=%d hours=%s wa=%s tg=%s" % (
            i + 1, t["id"][-6:], src, int(bool(rec.get("ok"))),
            ";".join(p.get("value", "") for p in rec.get("phones", [])),
            sum(1 for c in rec.get("contacts", []) if c.get("type") == "website"),
            rec.get("schedule"), rec.get("has_whatsapp"), rec.get("has_telegram")))
    fh.close()
    io.open(REPORT, "w", encoding="utf-8").write(json.dumps(stats, ensure_ascii=False, indent=1))
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
