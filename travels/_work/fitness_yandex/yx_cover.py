# -*- coding: utf-8 -*-
"""Coverage of Yandex Maps org catalogs outside Dushanbe.

usage: python yx_cover.py [slug ...]

For every city catalog and both queries we do what the Dushanbe grab did, but
small-scale: open, wait for a rendered list, scroll a few passes, and record
the union of snippets. A search that resolves to a single organisation is not
a failure here — Yandex opens that org's card directly, and "one card" is a
legitimate coverage answer for a small city, so it is recorded as kind=org.
Output: cover_rows.jsonl (one row per card) and cover_summary.tsv.
"""
import io
import json
import os
import subprocess
import sys
import time

EXE = os.path.expandvars(
    r"%APPDATA%\npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe")
HERE = os.path.dirname(os.path.abspath(__file__))
SESSION = os.environ.get("YX_SESSION", "yxm")
HOME = "https://yandex.kz/maps/"

CITIES = {
    "khujand": ("https://yandex.kz/maps/10322/khujand/search/{q}/", "Худжанд"),
    "kulob": ("https://yandex.kz/maps/20882/kulob/search/{q}/", "Куляб"),
    "bohtar": ("https://yandex.kz/maps/10319/bohtar/search/{q}/", "Бохтар"),
    "tursunzoda": ("https://yandex.kz/maps/21107/tursunzoda/search/{q}/",
                   "Турсунзаде"),
}
QUERIES = [(1, "gym", "Тренажерный зал"), (2, "fitnes", "Фитнес")]

READ = io.open(os.path.join(HERE, "yx_collect2.js"), encoding="utf-8").read()


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


def open_ready(url, budget=300):
    started, backoff, attempt = time.time(), 5, 0
    st = None
    while time.time() - started < budget:
        attempt += 1
        if attempt > 1:
            op(HOME)
            time.sleep(3)
        op(url)
        for _ in range(12):
            time.sleep(2)
            st = ev('(() => JSON.stringify({url: location.href, title: document.title,'
                    ' snippets: document.querySelectorAll("li.search-snippet-view").length,'
                    ' scroll: document.querySelectorAll(".scroll__container").length,'
                    ' org: /\\/maps\\/org\\//.test(location.href)}))()')
            if st["snippets"] or st["org"]:
                return st
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)
    return st


def main():
    wanted = sys.argv[1:] or list(CITIES)
    qlines = io.open(os.path.join(HERE, "_q.txt"), encoding="utf-8").read().splitlines()
    rows = []
    for slug in wanted:
        base, cname = CITIES[slug]
        for line, qname, qlabel in QUERIES:
            url = base.format(q=qlines[line - 1].strip())
            st = open_ready(url)
            kind = "org" if (st and st["org"]) else ("list" if st and st["snippets"] else "none")
            items = {}
            if kind == "list":
                for _ in range(8):
                    data = ev(READ)
                    for it in data.get("items", []):
                        key = it.get("id") or it.get("href")
                        if key:
                            items.setdefault(key, it)
                    if data["top"] + data["ch"] >= data["sh"] - 8:
                        break
                    time.sleep(1.0)
                print("%s/%s: list %d" % (slug, qname, len(items)), flush=True)
            else:
                one = ev('(() => {const h=document.querySelector("h1");'
                         'const c=document.querySelector("[data-coordinates]");'
                         'return JSON.stringify({name: h ? h.textContent.trim() : null,'
                         ' href: location.href.split("?")[0], coords: c ? c.getAttribute("data-coordinates") : null,'
                         ' text: (document.body.innerText||"").slice(0,400)});})()')
                items[one["href"]] = {"id": None, "href": one["href"],
                                      "name": one["name"], "coords": one["coords"],
                                      "text": one["text"]}
                print("%s/%s: %s -> %s" % (slug, qname, kind,
                                           json.dumps(one["name"], ensure_ascii=True)), flush=True)
            for it in items.values():
                rows.append({"city": slug, "city_ru": cname, "query": qlabel,
                             "kind": kind, "id": it.get("id"),
                             "href": it.get("href"), "name": it.get("name"),
                             "coords": it.get("coords"), "text": it.get("text")})
    with io.open(os.path.join(HERE, "cover_rows.jsonl"), "w", encoding="utf-8",
                 newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("rows=%d -> cover_rows.jsonl" % len(rows))


if __name__ == "__main__":
    main()
