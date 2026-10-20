# -*- coding: utf-8 -*-
"""Navigate the yxm session to a Yandex Maps Dushanbe search URL.

usage: python yx_nav.py <qfile_line_no>   (queries read percent-encoded from _q.txt)

URL template discovered to work in this environment:
  https://yandex.kz/maps/10318/dushanbe/search/<encoded query>/?ll=..&sll=..&z=12
Keeping the query ASCII (percent-encoded) avoids PowerShell/Cyrillic mangling.
"""
import io
import os
import subprocess
import sys

EXE = os.path.expandvars(
    r"%APPDATA%\npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe")
HERE = os.path.dirname(os.path.abspath(__file__))
QFILE = os.path.join(HERE, "_q.txt")

BASE = "https://yandex.kz/maps/10318/dushanbe/search/{q}/?ll=68.787000%2C38.559800&sll=68.787000%2C38.559800&z=12"


def main():
    idx = int(sys.argv[1]) - 1
    q = io.open(QFILE, encoding="utf-8").read().splitlines()[idx].strip()
    url = BASE.format(q=q)
    p = subprocess.run([EXE, "--session", "yxm", "open", url],
                       capture_output=True)
    print(url)
    out = p.stdout.decode("utf-8", "replace").strip()
    sys.stdout.buffer.write(out.encode("utf-8", "replace") + b"\n")
    if p.returncode != 0:
        sys.stdout.buffer.write(
            p.stderr.decode("utf-8", "replace").strip()[:400].encode("utf-8", "replace") + b"\n")
    return p.returncode


if __name__ == "__main__":
    sys.exit(main())
