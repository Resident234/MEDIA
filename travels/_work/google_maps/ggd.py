# -*- coding: utf-8 -*-
"""Shared Google Maps driver: primitives used by every domain collector.

All functions operate on the persistent `ggm` agent-browser session. Every
call is a subprocess to the native agent-browser executable so nothing is
kept in Python memory across invocations.
"""
import io
import json
import os
import re
import subprocess
import sys
import time

EXE = os.path.expandvars(
    r"%APPDATA%\npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe")
HERE = os.path.dirname(os.path.abspath(__file__))
SESSION = os.environ.get("GM_SESSION", "ggm")

_HARVEST_JS = io.open(os.path.join(HERE, "gm_harvest.js"), encoding="utf-8").read()
_CARD_JS = io.open(os.path.join(HERE, "gm_card.js"), encoding="utf-8").read()

_PROBE = io.open(os.path.join(HERE, "gm_probe.js"), encoding="utf-8").read()
_SCROLL = io.open(os.path.join(HERE, "gm_scroll.js"), encoding="utf-8").read()


def ev(js):
    p = subprocess.run([EXE, "--session", SESSION, "eval", "--stdin"],
                       input=js.encode("utf-8"), capture_output=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError("eval rc=%d %s" %
                           (p.returncode, p.stderr.decode("utf-8", "replace")[:200]))
    v = json.loads(p.stdout.decode("utf-8", "replace").strip())
    while isinstance(v, str):
        v = json.loads(v)
    return v


def op(url):
    subprocess.run([EXE, "--session", SESSION, "open", url],
                   capture_output=True, timeout=60)


def warm():
    """Ensure the browser session is alive by hitting the maps home page."""
    op("https://www.google.com/maps/?hl=ru")
    for _ in range(10):
        time.sleep(2)
        try:
            st = ev(_PROBE)
            if st.get("h1") or "maps" in (st.get("url") or ""):
                return st
        except Exception:
            pass
    return None


def search(url, budget=300, tries=4):
    """Open search URL, wait for feed anchors, handle bot-walls with retry.

    Returns the first harvest dict or None if never ready.
    """
    backoff = 8
    for t in range(tries):
        if t > 0:
            warm()
            time.sleep(backoff)
            backoff = min(backoff * 2, 90)
        op(url)
        started = time.time()
        while time.time() - started < 90:
            time.sleep(2)
            try:
                st = ev(_PROBE)
            except Exception:
                continue
            if st.get("capthcha"):
                break
            if st.get("anchors", 0) >= 3 and st.get("feed", 0) >= 1:
                return harvest_all()
            if st.get("h1") and "/maps/place/" in (st.get("url") or ""):
                return {"single": True, "items": [], "count": 0}
    return None


def harvest_all(passes=30, settle=2.5):
    """Scroll the feed and accumulate unique items until bottom."""
    all_items = {}
    bottom_count = 0
    for i in range(passes):
        try:
            d = ev(_HARVEST_JS)
        except Exception:
            break
        for it in d.get("items", []):
            all_items.setdefault(it["fid"], it)
        if d.get("st", 0) + d.get("ch", 0) >= d.get("sh", 0) - 8:
            bottom_count += 1
            if bottom_count >= 3 and len(all_items) >= d.get("count", 0):
                break
        else:
            bottom_count = 0
        try:
            ev(_SCROLL)
        except Exception:
            break
        time.sleep(settle)
    return {"items": list(all_items.values()), "count": len(all_items)}


def card(url, budget=180, tries=3):
    """Open a place card page and extract contact fields."""
    backoff = 8
    for t in range(tries):
        if t > 0:
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
        op(url)
        started = time.time()
        while time.time() - started < 60:
            time.sleep(2)
            try:
                st = ev(_PROBE)
            except Exception:
                continue
            if st.get("capthcha"):
                break
            if "/maps/place/" in (st.get("url") or "") and st.get("h1"):
                try:
                    return ev(_CARD_JS)
                except Exception:
                    break
    return None


def encode_query(q):
    from urllib.parse import quote
    return quote(q, safe="")


def search_url(q, city=None, near=None):
    text = q if not city else (q + " " + city)
    if near:
        return ("https://www.google.com/maps/search/%s/@%s,14z/data=!"
                "3m1!4b1?hl=ru&entry=ttu" % (encode_query(text), near))
    return "https://www.google.com/maps/search/%s?hl=ru" % encode_query(text)
