# -*- coding: utf-8 -*-
"""8 неподтверждённых банков → Yandex Maps → вытащить WA/Telegram/hotline.

usage: python probe_8.py            # весь список
       python probe_8.py --retest   # добрать пропущенные
       python probe_8.py <key>      # только один

Канал: yxd.open_ready() (тот же Windows-бинарь agent-browser-win32-x64.exe,
сессия YX_SESSION=yxbanks, отдельная от places_yandex).

Для каждого банка ищем головной офис в Душанбе; на Yandex Maps если карточка
одна — она открывается сразу, если список — берём первую. Парсим DOM:
  - <a href*="wa.me"> или <a href*="api.whatsapp.com"> → WhatsApp
  - <a href*="t.me"> или <a href*="telegram.me"> → Telegram
  - текст вида +992 XX XXX XX XX в innerText
"""
import io
import json
import os
import re
import sys
import time
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "places_yandex"))
os.environ["YX_SESSION"] = os.environ.get("YX_SESSION", "yxbanks5")
import yxd  # noqa: E402

OUT = os.path.join(HERE, "hotlines_extra.jsonl")
LOG = os.path.join(HERE, "probe.log")

# 8 неподтверждённых банков (head offices в Душанбе)
BANKS = [
    # key, display, yx query (Dushanbe)
    (u"Душанбе-Сити-Банк",
     u"Душанбе Сити Банк головной офис",
     u"Душанбе Сити Банк"),
    (u"IBT",
     u"IBT Международный банк Таджикистана",
     u"Международный банк Таджикистана IBT"),
    (u"Ориёнбанк",
     u"Ориёнбонк головной офис",
     u"Ориёнбанк Рудаки"),
    (u"Пайванд",
     u"Пайванд Групп",
     u"Пайванд группа"),
    (u"Тахвидбанк",
     u"Тавхидбанк первый исламский",
     u"Тавхидбанк"),
    (u"Эсхата",
     u"Банк Эсхата головной офис",
     u"Банк Эсхата"),
    (u"NBT",
     u"Национальный банк Таджикистана",
     u"Национальный банк Таджикистана"),
    (u"Ишкола",
     u"Ишкола банк",
     u"Ишкола банк"),
]

# ORG v2 — снимает WA/TG якоря
ORG2 = (
    '(() => {'
    ' const h = document.querySelector("h1");'
    ' const c = document.querySelector("[data-coordinates]");'
    ' const name = h ? h.textContent.trim() : null;'
    ' const coords = c ? c.getAttribute("data-coordinates") : null;'
    ' const wa = [].slice.call(document.querySelectorAll('
    '   "a[href*=\'wa.me\'],a[href*=\'api.whatsapp.com\']"))'
    '   .map(a => a.href);'
    ' const tg = [].slice.call(document.querySelectorAll('
    '   "a[href*=\'t.me/\'],a[href*=\'telegram.me/\']"))'
    '   .map(a => a.href);'
    ' const phones = [].slice.call(document.querySelectorAll('
    '   "a[href^=\'viber://\'],a[href^=\'tel:\']"))'
    '   .map(a => a.href.replace(/^tel:/,""));'
    ' const url = location.href.split("?")[0];'
    ' return JSON.stringify({name, coords, url, wa, tg, phones,'
    '   text: (document.body.innerText||"").slice(0,1500)});})()'
)

PHONE_RE = re.compile(r"\+?992[\s\-\(]?(\d{2,3})[\s\-\)]?[\s\-]?(\d{3})[\s\-]?(\d{2})[\s\-]?(\d{2})")


def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def log(msg):
    line = "[%s] %s\n" % (time.strftime("%H:%M:%S"), msg)
    sys.stdout.write(a(line))
    sys.stdout.flush()
    io.open(LOG, "a", encoding="utf-8").write(line)


def search_url(query):
    # yandex.ru/maps/9643/dushanbe/search/<q> — тот же city-id что и places_yandex
    return "https://yandex.kz/maps/10318/dushanbe/search/%s/" % quote(query, safe="")


def parse_wa_tg_from_text(text):
    """Fallback: вытащить wa.me/t.me прямо из innerText."""
    wa = []
    tg = []
    for m in re.finditer(r"wa\.me/(\+?\d{9,15})", text):
        wa.append("https://wa.me/" + re.sub(r"\D", "", m.group(1)))
    for m in re.finditer(r"(?:t\.me|telegram\.me)/(\+?\d{9,15}|[A-Za-z][A-Za-z0-9_]{3,31})",
                          text):
        tg.append("https://t.me/" + m.group(1))
    ph = []
    for g in PHONE_RE.findall(text):
        d = re.sub(r"\D", "", "".join(g))
        if len(d) == 9:
            ph.append("992" + d)
    return wa, tg, list(set(ph))


def one_bank(key, display, yxq):
    qurl = search_url(yxq)
    log("QUERY %s → %s" % (key, qurl))
    st = yxd.open_ready(qurl, budget=600)
    rec = {"key": key, "display": display, "yx_url": qurl, "ts": time.strftime("%Y-%m-%d %H:%M")}
    if st is None:
        rec["status"] = "timeout"
        return rec
    if st.get("none"):
        rec["status"] = "empty"
        return rec
    # Если список — берём первую карточку и переходим в неё.
    if st.get("snippets") and not st.get("org"):
        first_href_js = (
            '(() => {'
            ' const li = document.querySelector("li.search-snippet-view");'
            ' if (!li) return JSON.stringify({href:null});'
            ' const a = li.querySelector("a[href*=\\"/maps/\\"]");'
            ' return JSON.stringify({href: a ? a.href.split("?")[0] : null});})()'
        )
        try:
            item = json.loads(yxd.ev(first_href_js))
        except Exception:
            item = {"href": None}
        if item.get("href"):
            yxd.op(quote(item["href"].encode("utf-8"), safe=":/?&=%,"))
            for _ in range(15):
                time.sleep(2)
                st2 = yxd.ev(yxd.STATE)
                if st2.get("org"):
                    break
    if not st.get("org"):
        try:
            org = yxd.ev(ORG2)
        except Exception as e:
            rec["status"] = "noorg %s" % type(e).__name__
            return rec
    else:
        try:
            org = yxd.ev(ORG2)
        except Exception as e:
            rec["status"] = "orgeror %s" % type(e).__name__
            return rec
    text = org.get("text", "") or ""
    wa = list(org.get("wa") or [])
    tg = list(org.get("tg") or [])
    phones = list(org.get("phones") or [])
    if not wa or not tg:
        w2, t2, p2 = parse_wa_tg_from_text(text)
        wa = wa or w2
        tg = tg or t2
        phones = phones or p2
    rec.update({
        "status": "ok",
        "org_name": org.get("name"),
        "org_url": org.get("url"),
        "org_coords": org.get("coords"),
        "whatsapp": wa,
        "telegram": tg,
        "phones": phones,
        "text_head": text[:600],
    })
    log("  -> name=%s wa=%d tg=%d ph=%d" % (a(org.get("name")), len(wa), len(tg), len(phones)))
    return rec


def main():
    only = None
    retest = False
    for arg in sys.argv[1:]:
        if arg == "--retest":
            retest = True
        else:
            only = arg.lower()
    done_keys = set()
    if os.path.exists(OUT) and retest:
        for l in io.open(OUT, encoding="utf-8"):
            try:
                r = json.loads(l)
                if r.get("status") == "ok" and (r.get("whatsapp") or r.get("telegram")):
                    done_keys.add(r.get("key"))
            except ValueError:
                pass
    fh = io.open(OUT, "a" if retest else "w", encoding="utf-8", newline="\n")
    n_ok = n_wa = 0
    for key, disp, yxq in BANKS:
        if only and only not in key.lower() and only not in disp.lower():
            continue
        if key in done_keys:
            log("skip %s (already have WA/TG)" % key)
            continue
        try:
            rec = one_bank(key, disp, yxq)
        except Exception as e:
            log("EXC %s: %s" % (key, type(e).__name__))
            rec = {"key": key, "display": disp, "status": "exc", "err": str(e)[:200]}
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        if rec.get("status") == "ok":
            n_ok += 1
        if rec.get("whatsapp"):
            n_wa += 1
        time.sleep(3)  # cooldown между банками
    fh.close()
    log("finish: %d banks processed, %d with WA, %d with TG-or-phone" % (
        n_ok, n_wa, sum(1 for _ in [])))


if __name__ == "__main__":
    main()
