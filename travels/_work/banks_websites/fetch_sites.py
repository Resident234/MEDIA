# -*- coding: utf-8 -*-
"""Официальный домен банка → попытка вытащить WhatsApp/Telegram/hotline.

usage: python fetch_sites.py            # весь список
       python fetch_sites.py amonatbank # только один домен

Канал: обычный HTTP GET на base_url + типовые пути /contact /contacts /about
/footer /filialy /otdeleniya. Парсим HTML регулярками на wa.me, t.me,
api.whatsapp.com. Плюс вытаскиваем телефоны вида +992 XX XXX XX XX.

Некоторые сайты — SPA (Алиф, ДСБ). Если HTML пустой, пробуем `/api/...`
потом (этот скрипт SPA не рендерит). Для них — фолбэк на Yandex browser.
"""
import io
import json
import os
import re
import sys
import time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
BANKS = os.path.join(HERE, "_banks.txt")
OUT = os.path.join(HERE, "hotlines.jsonl")
LOG = os.path.join(HERE, "hotlines.log")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

PATHS = ["", "/contact", "/contacts", "/контакты", "/footer", "/about",
         "/about-us", "/aboutus", "/filialy", "/network", "/branches",
         "/offices", "/pages/contacts"]

WA_RE = re.compile(
    r"https?://(?:wa\.me|api\.whatsapp\.com/send\?phone=)(\+?\d{9,15})",
    re.IGNORECASE)
TG_RE = re.compile(
    r"https?://(?:t\.me|telegram\.me)/(\+?\d{9,15}|[A-Za-z][A-Za-z0-9_]{3,31})",
    re.IGNORECASE)
PHONE_RE = re.compile(
    r"(?:\+992|8[\s\-]*992)[\s\-]?(\(?\d{2,3}\)?)[\s\-]?(\d{3})[\s\-]?(\d{2})[\s\-]?(\d{2})")


def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def log(msg):
    line = "[%s] %s\n" % (time.strftime("%H:%M:%S"), msg)
    sys.stdout.write(a(line))
    sys.stdout.flush()
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(line)


def fetch(url, sess):
    try:
        r = sess.get(url, timeout=(15, 60), allow_redirects=True)
        if r.status_code != 200:
            return None, "http %d" % r.status_code
        return r.text, None
    except requests.RequestException as e:
        return None, "exc %s" % type(e).__name__


def scrape_bank(name, base_url, sess):
    """base_url: https://amonatbank.tj. Пробуем корень и /contact-пути."""
    merged = []
    errors = []
    for path in PATHS:
        url = base_url.rstrip("/") + path if path else base_url
        body, err = fetch(url, sess)
        if err:
            errors.append("%s: %s" % (path or "/", err))
            continue
        if body and len(body) > 500:
            merged.append((path, body))
            # ранний выход: если на первом же пути уже wa.me + t.me есть
            wa = WA_RE.findall(body)
            tg = TG_RE.findall(body)
            if wa and tg:
                break
        time.sleep(0.4)
    wa_set, tg_set = set(), set()
    for path, body in merged:
        for m in WA_RE.findall(body):
            digits = re.sub(r"\D", "", m)
            if digits.startswith("998") and len(digits) == 12:
                # узбекский формат? нормализуем
                pass
            if len(digits) == 9:
                digits = "992" + digits
            wa_set.add(digits)
        for m in TG_RE.findall(body):
            if m.startswith("+"):
                tg_set.add(("phone", re.sub(r"\D", "", m)))
            else:
                tg_set.add(("user", m))
    phones = set()
    for _, body in merged:
        for grp in PHONE_RE.findall(body):
            d = re.sub(r"\D", "", "".join(grp))
            if len(d) == 9:
                phones.add("992" + d)
    return {
        "bank": name,
        "base_url": base_url,
        "pages": [p for p, _ in merged],
        "errors": errors[:6],
        "whatsapp": sorted(wa_set),
        "telegram": sorted(tg_set),
        "phones": sorted(phones),
        "ts": time.strftime("%Y-%m-%d"),
    }


def main():
    filter_arg = None
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            filter_arg = arg.lower()
    if not os.path.exists(BANKS):
        print("missing _banks.txt")
        return 1
    rows = [l.strip() for l in io.open(BANKS, encoding="utf-8") if l.strip()]
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA,
                         "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                         "Accept-Language": "ru-RU,ru;q=0.8"})
    fh = io.open(OUT, "a", encoding="utf-8", newline="\n")
    done_urls = set()
    if os.path.exists(OUT):
        for l in io.open(OUT, encoding="utf-8"):
            try:
                r = json.loads(l)
                if r.get("whatsapp") or r.get("telegram"):
                    done_urls.add(r.get("base_url", ""))
            except ValueError:
                pass
    n_ok = n_tg = n_wa = 0
    for row in rows:
        parts = row.split("\t")
        if len(parts) < 2:
            continue
        name, base_url = parts[0], parts[1]
        if filter_arg and filter_arg not in base_url.lower():
            continue
        if base_url in done_urls:
            log("skip %s (already scraped with contacts)" % name)
            continue
        log("FETCH %s\t%s" % (name, base_url))
        rec = scrape_bank(name, base_url, sess)
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        log("  -> wa=%d tg=%d phones=%d pages=%d errs=%d" % (
            len(rec["whatsapp"]), len(rec["telegram"]),
            len(rec["phones"]), len(rec["pages"]), len(rec["errors"])))
        n_ok += 1
        if rec["whatsapp"]: n_wa += 1
        if rec["telegram"]: n_tg += 1
        time.sleep(0.6)
    fh.close()
    log("finish: %d banks, %d with wa, %d with tg" % (n_ok, n_wa, n_tg))


if __name__ == "__main__":
    main()
