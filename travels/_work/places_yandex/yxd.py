# -*- coding: utf-8 -*-
"""Shared Yandex Maps browser driver for the shopping pass.

Everything the fitness pass learned about this service is baked in here:

  * the CLI is the real Windows binary — the .cmd shim chokes on the `&` in
    Yandex URLs and the .ps1 is blocked by the execution policy;
  * long repeated navigations get throttled with a stub page whose entire body
    is the word "limited"; the stub clears after a detour through the maps home
    page plus a wait, and re-opening the target URL back-to-back does nothing;
  * the result list is virtualized (only the snippets inside the scroll window
    are in the DOM), so a full answer is the union of what each pass renders;
  * a search that matches exactly one organisation opens that card instead of a
    list — a legitimate answer, not a failure;
  * the console is cp866 and cannot print Cyrillic, so anything printed here is
    ASCII-escaped; Tajik/Russian text only ever goes into files.
"""
import io
import json
import os
import subprocess
import time

EXE = os.path.expandvars(
    r"%APPDATA%\npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe")
HERE = os.path.dirname(os.path.abspath(__file__))
SESSION = os.environ.get("YX_SESSION", "yxshop")
HOME = "https://yandex.kz/maps/"

# First pass rewinds the virtualized container so the head of the list is never
# skipped, later passes scroll one viewport forward.
COLLECT = io.open(os.path.join(os.path.dirname(HERE), "fitness_yandex",
                               "yx_collect2.js"), encoding="utf-8").read()

STATE = ('(() => JSON.stringify({url: location.href, title: document.title,'
         ' snippets: document.querySelectorAll("li.search-snippet-view").length,'
         ' scroll: document.querySelectorAll(".scroll__container").length,'
         ' none: /ничего не нашлось|Ничего не нашлось/.test(document.body.innerText||""),'
         ' org: /\\/maps\\/org\\//.test(location.href)}))()')

ORG = ('(() => {const h=document.querySelector("h1");'
       'const c=document.querySelector("[data-coordinates]");'
       'return JSON.stringify({name: h ? h.textContent.trim() : null,'
       ' href: location.href.split("?")[0], coords: c ? c.getAttribute("data-coordinates") : null,'
       ' text: (document.body.innerText||"").slice(0,900)});})()')


def ev(js):
    p = subprocess.run([EXE, "--session", SESSION, "eval", "--stdin"],
                       input=js.encode("utf-8"), capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:300])
    v = json.loads(p.stdout.decode("utf-8", "replace").strip())
    while isinstance(v, str):
        v = json.loads(v)
    return v


def op(url):
    subprocess.run([EXE, "--session", SESSION, "open", url], capture_output=True)


def show(text):
    """ASCII-safe console line for Cyrillic strings."""
    return json.dumps(text, ensure_ascii=True)


def open_ready(url, budget=300):
    """Open a search URL, working through the throttle stub; return page state."""
    import urllib.parse
    quoted = urllib.parse.quote(url.encode("utf-8"), safe=":/?&=%,")
    started, backoff, attempt = time.time(), 5, 0
    st = None
    while time.time() - started < budget:
        attempt += 1
        if attempt > 1:
            op(HOME)
            time.sleep(3)
        op(quoted)
        for _ in range(12):
            time.sleep(2)
            st = ev(STATE)
            if st["snippets"] or st["org"] or st["none"]:
                return st
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)
    return st


def harvest(url, passes=12, budget=300):
    """Return (kind, [items]) for one search URL."""
    st = open_ready(url, budget)
    if st is None:
        return "timeout", []
    if st["org"]:
        one = ev(ORG)
        return "org", [{"id": None, "href": one["href"], "name": one["name"],
                        "coords": one["coords"], "text": one["text"]}]
    if not st["snippets"]:
        return ("empty" if st["none"] else "none"), []
    items, seen = [], set()
    for _ in range(passes):
        data = ev(COLLECT)
        for it in data.get("items", []):
            key = it.get("id") or it.get("href")
            if key and key not in seen:
                seen.add(key)
                items.append(it)
        if data["top"] + data["ch"] >= data["sh"] - 8:
            break
        time.sleep(1.0)
    return "list", items
