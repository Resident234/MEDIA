# -*- coding: utf-8 -*-
"""Coverage probe: run both queries in every other Tajik city catalog.

usage: python yx_cities.py [slug ...]
City catalogs and their ids were harvested with yx_cityid.py (the geo card of
a city name exposes /maps/<id>/<slug>/ links). For each catalog we grab
"Тренажерный зал" (line 1 of _q.txt) and "Фитнес" (line 2) the same way the
Dushanbe lists were grabbed, writing <slug>_<qname>.jsonl.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CITIES = {
    "kulob": "https://yandex.kz/maps/20882/kulob/search/{q}/",
    "bohtar": "https://yandex.kz/maps/10319/bohtar/search/{q}/",
    "tursunzoda": "https://yandex.kz/maps/21107/tursunzoda/search/{q}/",
}
QUERIES = [(1, "gym"), (2, "fitnes")]


def main():
    wanted = sys.argv[1:] or list(CITIES)
    for slug in wanted:
        env = dict(os.environ, YX_BASE=CITIES[slug])
        for line, name in QUERIES:
            out = "%s_%s.jsonl" % (slug, name)
            print("=== %s / %s -> %s" % (slug, name, out), flush=True)
            p = subprocess.run(
                [sys.executable, os.path.join(HERE, "yx_grab.py"), str(line), out,
                 "120", "5", "1.0"],
                env=env, cwd=HERE, capture_output=True)
            tail = p.stdout.decode("utf-8", "replace").splitlines()[-3:]
            sys.stdout.buffer.write(("\n".join(tail) + "\n").encode(
                "ascii", "backslashreplace"))
            if p.returncode != 0:
                sys.stdout.buffer.write(
                    ("ERR " + p.stderr.decode("utf-8", "replace")[-300:] + "\n"
                     ).encode("ascii", "backslashreplace"))


if __name__ == "__main__":
    main()
