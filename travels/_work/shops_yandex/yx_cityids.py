# -*- coding: utf-8 -*-
"""Find the Yandex Maps city catalog (id/slug) for the towns named in раздел 8.

usage: python yx_cityids.py [Name ...]     (default: _cities.txt, one per line)

A place name typed into the search box resolves into a geo card, and that card
carries links to the city's own catalog (/maps/<id>/<slug>/...). We search the
name inside the Dushanbe catalog and harvest whatever catalog the redirect
exposes, recording the final URL and page title so a wrong-city hit is visible
rather than silent. Output: _cityids.json.
"""
import json
import os
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from yxd import ev, op, show, HOME  # noqa: E402

HARVEST = """(() => {
  const s = new Set();
  for (const a of document.querySelectorAll('a')) {
    const h = a.getAttribute('href') || '';
    const m = h.match(/^\\/maps\\/(\\d+)\\/([a-z0-9-]+)\\//);
    if (m) s.add(m[1] + '/' + m[2]);
  }
  const geo = (location.href.match(/\\/maps\\/geo\\/(\\d+)/) || [])[1] || null;
  return JSON.stringify({url: location.href, title: document.title,
                         geo: geo, cats: [...s]});
})()"""


def main():
    names = sys.argv[1:] or [x.strip() for x in
                             open(os.path.join(HERE, "_cities.txt"), encoding="utf-8")
                             if x.strip()]
    out = {}
    path = os.path.join(HERE, "_cityids.json")
    if os.path.exists(path):
        out = json.load(open(path, encoding="utf-8"))
    for name in names:
        if name in out and out[name].get("cats"):
            continue
        q = urllib.parse.quote(name.encode("utf-8"))
        url = ("https://yandex.kz/maps/10318/dushanbe/search/%s/"
               "?ll=68.787000%%2C38.559800&z=9" % q)
        got = None
        for attempt in range(1, 5):
            op(HOME)
            time.sleep(3)
            op(url)
            for _ in range(10):
                time.sleep(2)
                got = ev(HARVEST)
                if got["title"] and (got["url"] != url or got["cats"]):
                    break
            if got["cats"]:
                break
            time.sleep(5 * attempt)
        out[name] = got
        print("%-28s -> %s" % (
            show(name), json.dumps({"cats": got.get("cats"), "geo": got.get("geo"),
                                    "title": (got.get("title") or "")[:60]},
                                   ensure_ascii=True)[:300]), flush=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
