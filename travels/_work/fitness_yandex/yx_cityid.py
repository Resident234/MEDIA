# -*- coding: utf-8 -*-
"""Find a Yandex Maps city catalog (id/slug) by searching the city name.

usage: python yx_cityid.py <CityName> [CityName2 ...]
Yandex resolves a place name typed into the search box into a geo card whose
links carry the city catalog prefix (/maps/<id>/<slug>/...), so this walks the
redirected page and harvests every distinct catalog it exposes.
"""
import json
import os
import subprocess
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
EXE = os.path.expandvars(
    r"%APPDATA%\npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe")
SESSION = os.environ.get("YX_SESSION", "yxm")

HARVEST = """(() => {
  const s = new Set();
  for (const a of document.querySelectorAll('a')) {
    const h = a.getAttribute('href') || '';
    const m = h.match(/^\\/maps\\/(\\d+)\\/([a-z0-9-]+)\\//);
    if (m) s.add(m[1] + '/' + m[2]);
  }
  return JSON.stringify({url: location.href, title: document.title,
                         cats: [...s]});
})()"""


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


def main():
    names = sys.argv[1:]
    if not names:
        # Cyrillic command-line args get mangled by the cp866 console, so the
        # city list lives in a file written with \u escapes.
        names = [x.strip() for x in open(os.path.join(HERE, "_cities.txt"),
                                         encoding="utf-8") if x.strip()]
    res = {}
    for name in names:
        q = urllib.parse.quote(name.encode("utf-8"))
        url = ("https://yandex.kz/maps/10318/dushanbe/search/%s/"
               "?ll=68.787000%%2C38.559800&z=9" % q)
        got = None
        for attempt in range(1, 6):
            op("https://yandex.kz/maps/")
            time.sleep(3)
            op(url)
            for _ in range(10):
                time.sleep(2)
                got = ev(HARVEST)
                if got["title"] and got["url"] != url:
                    break
            if got["cats"]:
                break
            time.sleep(5 * attempt)
        res[name] = got
        print("%-12s -> %s" % (name.encode("ascii", "backslashreplace").decode(),
                               json.dumps(got, ensure_ascii=True)[:400]), flush=True)
    with open(os.path.join(HERE, "_cityids.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
