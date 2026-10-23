# -*- coding: utf-8 -*-
"""Shared Yandex Maps browser driver for the shopping pass.

Everything the fitness pass learned about this service is baked in here:

  * the CLI is the real Windows binary — the .cmd shim chokes on the `&` in
    Yandex URLs and the .ps1 is blocked by the execution policy;
  * long repeated navigations get throttled with a stub page whose entire body
    is the word "limited"; the stub clears after a detour through the maps home
    page plus a wait, and re-opening the target URL back-to-back does nothing;
  * the answer is read from the ``state-view`` JSON snapshot, not from the DOM:
    it holds all 25 objects of a page with phones, socials and rating, and the
    panel itself never shows more than 25 per query, so the rest comes from the
    ``?page=N`` links of a catalog search;
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
SESSION = os.environ.get("YX_SESSION", "yxhousing")
# Домен переключается через YX_HOST: с чужого IP yandex.kz отдаёт заглушку
# «limited» заметно чаще, чем yandex.ru, при том же наборе данных.
HOST = os.environ.get("YX_HOST", "https://yandex.ru").rstrip("/")
HOME = HOST + "/maps/"

# The business objects the page keeps in its state snapshot: they carry phones,
# socialLinks, ratingData and categories, so one list pass covers what a card
# visit would have added.
COLLECT_STATE = io.open(os.path.join(HERE, "yx_state.js"),
                        encoding="utf-8").read()

STATE = ('(() => JSON.stringify({url: location.href, title: document.title,'
         ' snippets: document.querySelectorAll("li.search-snippet-view").length,'
         ' scroll: document.querySelectorAll(".scroll__container").length,'
         ' lim: /^limited$/.test((document.body.innerText||"").trim()),'
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


def cool(wait=30, rounds=4):
    """Sit out the throttle stub. Returns True once the stub is gone."""
    for i in range(rounds):
        op(HOME)
        time.sleep(wait)
        st = ev(STATE)
        if not st.get("lim"):
            return True
        print("throttled, cooling %ds (round %d)" % (wait * (i + 1), i + 1))
    return False


def open_ready(url, budget=75, tries=2):
    """Open a search URL; return page state, or a state with ``lim`` set.

    Две попытки — и хватит: если антибот-заглушка не ушла, дешевле отдать
    ход наверх (там решают, ждать или идти дальше), чем сидеть в ретраях.
    """
    import urllib.parse
    quoted = urllib.parse.quote(url.encode("utf-8"), safe=":/?&=%,")
    started, st = time.time(), None
    for attempt in range(tries):
        if attempt:
            op(HOME)
            time.sleep(8)
        op(quoted)
        for _ in range(15):
            time.sleep(2)
            st = ev(STATE)
            if st["snippets"] or st["org"] or st["none"]:
                return st
            if st.get("lim"):
                break
        if time.time() - started > budget:
            break
    return st


def harvest_state(url, budget=80, pages=12, pause=4, tries=2):
    """Return (kind, items, total, base, complete).

    kind: list | empty | none | org | timeout | throttled.
    The panel keeps only 25 objects per page but the page state already
    carries all of them, so no scrolling is needed. For catalog searches
    (``/maps/<id>/<slug>/search/<query>/``) the rest is taken page by page
    via its own ``?page=N`` links. ``base`` is the search URL without the
    query string: its ``.../search/`` prefix is what later queries for the
    same town reuse, which saves a redirect and a second page load.

    ``totalResultCount`` в выдаче плавает от загрузки к загрузке (45, 89,
    131 для одного запроса), поэтому конец списка определяется не им, а
    страницей без новых id. ``complete`` — дошли ли до такого конца.
    """
    st = open_ready(url, budget, tries)
    if st is None:
        return "timeout", [], None, None, False
    if st.get("lim"):
        return "throttled", [], None, None, False
    if st["org"]:
        one = ev(ORG)
        return ("org", [{"id": None, "href": one["href"], "title": one["name"],
                         "coords": one["coords"]}], 1, None, True)
    if not st["snippets"] and not st["none"]:
        return "none", [], None, None, False

    items, seen, total = [], set(), None

    def add(data):
        new = 0
        for it in data.get("items") or []:
            key = it.get("id") or it.get("title")
            if key and key not in seen:
                seen.add(key)
                items.append(it)
                new += 1
        return new

    data = ev(COLLECT_STATE)
    total = data.get("total") or None
    add(data)

    base = st["url"].split("?")[0]
    paged = "/search/" in base
    # Панель отдаёт ровно 25 на страницу: меньше — значит страниц больше нет.
    complete = not paged or len(items) < 25
    page = 1
    while paged and not complete and page < pages:
        page += 1
        time.sleep(pause)
        nst = open_ready("%s?page=%d" % (base, page), budget=70, tries=1)
        if nst is None or nst.get("lim"):
            break
        if not nst["snippets"]:
            # страница за последней: Яндекс показывает «ничего не нашлось»
            complete = bool(nst.get("none"))
            break
        if add(ev(COLLECT_STATE)) == 0:
            complete = True
            break
    return ("list" if items else "empty"), items, total, (
        base if paged else None), complete


def search_url(query, cat=None, ll=None, z=None, page=1):
    """Build a search URL: city catalog, or the whole map at a given viewport."""
    import urllib.parse
    q = urllib.parse.quote(query.encode("utf-8"))
    if cat:
        url = "%s/maps/%s/search/%s/" % (HOST, cat, q)
        if page > 1:
            url += "?page=%d" % page
        return url
    url = "%s/maps/?text=%s" % (HOST, q)
    if ll:
        url += "&ll=%s&z=%s" % (ll.replace(",", "%2C"), z)
    if page > 1:
        url += "&p=%d" % page
    return url


if __name__ == "__main__":
    # python yxd.py "Гостиница" [--cat 10318/dushanbe | --ll 71.0,38.8 --z 6]
    import argparse
    ap = argparse.ArgumentParser(description="probe one Yandex Maps search")
    ap.add_argument("query")
    ap.add_argument("--cat")
    ap.add_argument("--ll")
    ap.add_argument("--z", type=int)
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--pages", type=int, default=8)
    ap.add_argument("--budget", type=int, default=300)
    a = ap.parse_args()
    u = search_url(a.query, a.cat, a.ll, a.z, a.page)
    print("url", u.encode("ascii", "backslashreplace").decode("ascii"))
    cool(20, 3)
    kind, got, total, base, complete = harvest_state(
        u, budget=a.budget, pages=a.pages)
    print("kind=%s n=%d total=%s complete=%s base=%s" % (
        kind, len(got), total, complete,
        base.encode("ascii", "backslashreplace").decode("ascii")
        if base else None))
    for it in got[:5]:
        print(show("%s | %s | %s" % (it.get("title"), it.get("address"),
                                     (it.get("phones") or "")))[:300])
