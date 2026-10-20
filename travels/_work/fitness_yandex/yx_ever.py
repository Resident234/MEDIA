# -*- coding: utf-8 -*-
"""Eval an inline JS expression in the yxm session, print ASCII-safe result.

usage: python yx_ever.py "<js>"
Avoids having to keep one .js file per probe; output is escaped so the cp866
console never sees a non-ASCII byte.
"""
import json
import os
import subprocess
import sys

EXE = os.path.expandvars(
    r"%APPDATA%\npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe")
SESSION = os.environ.get("YX_SESSION", "yxm")


def ev(js, session=SESSION):
    p = subprocess.run([EXE, "--session", session, "eval", "--stdin"],
                       input=js.encode("utf-8"), capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:300])
    v = json.loads(p.stdout.decode("utf-8", "replace").strip())
    while isinstance(v, str):
        v = json.loads(v)
    return v


if __name__ == "__main__":
    js = sys.argv[1]
    if not js.startswith("("):
        js = "(() => { %s })()" % js
    sys.stdout.buffer.write(
        json.dumps(ev(js), ensure_ascii=True, indent=1).encode()[:3000])
