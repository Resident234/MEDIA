# -*- coding: utf-8 -*-
"""Отправить стандартный вопрос на 10 подтверждённых WA-номеров банков.

Требует уже залогиненной WhatsApp Web-сессии wasend (или YX_SESSION_WA).

usage:
  python send_wa.py --dry     # только показать, что будем слать
  python send_wa.py           # отправить всем
  python send_wa.py --only КБТ,Хумо   # только указанным ключам
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
HOTLINES = os.path.join(HERE, "..", "banks_websites", "hotlines_curated.jsonl")
LOG = os.path.join(HERE, "sent.log")
STATE = os.path.join(HERE, "sent_state.json")

EXE = os.path.expandvars(
    r"%APPDATA%\npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe")
SESSION = os.environ.get("WA_SESSION", "wasend")

WA_MESSAGE = (u"\u0417\u0434\u0440\u0430\u0441\u0442\u0432\u0443\u0439\u0442\u0435. "
              u"\u041e\u0442\u043a\u0440\u044b\u0432\u0430\u0435\u0442\u0435 "
              u"\u043b\u0438 \u0432\u044b \u043a\u0430\u0440\u0442\u044b "
              u"\u043d\u0435\u0440\u0435\u0437\u0438\u0434\u0435\u043d\u0442\u0430\u043c "
              u"\u0438 \u043d\u0430 \u043a\u0430\u043a\u0438\u0445 "
              u"\u0443\u0441\u043b\u043e\u0432\u0438\u044f\u0445 ?")
WA_ENCODED = urllib.parse.quote(WA_MESSAGE.encode("utf-8"))

# JS проверяет: чат открыт, композер содержит текст >10 симв.
CHECK_JS = (
    '(() => {'
    'const box = document.querySelector('
    '  "div[contenteditable=true][role=textbox]");'
    'const chat = document.querySelector('
    '  "#main span[dir=auto], #main h1 span[dir=auto]");'
    'return JSON.stringify({'
    '  hasBox: !!box,'
    '  boxTxt: box ? (box.innerText || "").slice(0,150) : null,'
    '  title: chat ? chat.innerText.trim() : null'
    '});})()'
)

# Клик по кнопке "Отправить" (unicode escape чтобы не терять cp866).
SEND_JS = (
    '(() => {'
    'const target = "\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c";'
    'const b = Array.from(document.querySelectorAll("button,[role=button]"))'
    '  .filter(x => (x.getAttribute("aria-label")||x.innerText||"").trim()'
    '               === target);'
    'if (!b.length) return JSON.stringify({e:"no send"});'
    'b[0].click();'
    'return JSON.stringify({ok:true,n:b.length});})()'
)


def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def ev(js, timeout=15):
    try:
        p = subprocess.run([EXE, "--session", SESSION, "eval", "--stdin"],
                           input=js.encode("utf-8"),
                           capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"e": "ev_timeout"}
    if p.returncode != 0:
        return {"e": "ev_err", "m": p.stderr.decode("utf-8", "replace")[:200]}
    raw = p.stdout.decode("utf-8", "replace").strip()
    try:
        v = json.loads(raw)
        while isinstance(v, str):
            v = json.loads(v)
        return v
    except ValueError:
        return {"e": "parse", "raw": raw[:200]}


def op(url, timeout=30):
    try:
        subprocess.run([EXE, "--session", SESSION, "open", url],
                       capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        pass  # SPA навигация может не закрыть stdout — это нормально


def log(msg):
    line = "[%s] %s\n" % (time.strftime("%H:%M:%S"), msg)
    sys.stdout.write(a(line))
    sys.stdout.flush()
    io.open(LOG, "a", encoding="utf-8").write(line)


def send_web_url(digits):
    return "https://web.whatsapp.com/send?phone=%s&text=%s" % (digits,
                                                                WA_ENCODED)


def one_bank(rec):
    key = rec["key"]
    name = rec.get("name") or key
    digits = rec.get("wa_phone")
    if not digits:
        log("skip %s (no digits)" % key)
        return {"key": key, "status": "no_digits"}
    url = send_web_url(digits)
    log("SEND %s [%s] -> %s" % (key, digits, name))
    op(url)
    st = None
    for _ in range(20):  # 40 сек максимум
        time.sleep(2)
        st = ev(CHECK_JS)
        if st.get("hasBox") and st.get("boxTxt") and len(st["boxTxt"]) > 10:
            break
    if not (st and st.get("hasBox") and st.get("boxTxt")):
        log("  FAIL no chat: %s" % a(st))
        return {"key": key, "status": "no_chat", "state": st, "url": url}
    title = st.get("title")
    log("  chat=%s composer=%dch" % (a(title), len(st.get("boxTxt") or "")))
    r = ev(SEND_JS)
    if not r.get("ok"):
        log("  FAIL send: %s" % a(r))
        return {"key": key, "status": "no_send", "send": r, "url": url}
    log("  SENT")
    return {"key": key, "status": "sent", "digits": digits, "url": url,
            "chat_title": title}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--gap", type=int, default=45, help="секунд между банками")
    args = ap.parse_args()

    rows = [json.loads(l) for l in io.open(HOTLINES, encoding="utf-8") if l.strip()]
    rows = [r for r in rows if r.get("verified_whatsapp") and r.get("wa_phone")]
    if args.only:
        keep = {s.strip().lower() for s in args.only.split(",")}
        rows = [r for r in rows
                if r["key"].lower() in keep
                or r.get("name", "").lower() in keep]

    log("planned %d banks: %s" % (len(rows),
                                  ", ".join(r["key"] for r in rows)))
    if args.dry:
        for r in rows:
            log("  dry %s %s %s" % (r["key"], r["wa_phone"], r["wa_url"]))
        return

    prev = {}
    if os.path.exists(STATE):
        try:
            prev = json.load(io.open(STATE, encoding="utf-8"))
        except ValueError:
            prev = {}

    results = []
    for i, rec in enumerate(rows):
        if rec["key"] in prev.get("sent_keys", []):
            log("skip %s (already sent)" % rec["key"])
            continue
        r = one_bank(rec)
        results.append(r)
        if r["status"] == "sent":
            prev.setdefault("sent_keys", []).append(r["key"])
            json.dump(prev, io.open(STATE, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
        if i < len(rows) - 1 and r["status"] == "sent":
            log("  sleep %d" % args.gap)
            time.sleep(args.gap)

    n_sent = sum(1 for r in results if r["status"] == "sent")
    log("DONE: %d sent, %d failed" % (n_sent, len(results) - n_sent))


if __name__ == "__main__":
    main()
