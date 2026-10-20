# -*- coding: utf-8 -*-
"""Eval a JS file in a session and write the decoded result to an output file.

usage: python yx_eval.py <session> <js_file> <out_file>
"""
import io
import json
import os
import subprocess
import sys

EXE = os.path.expandvars(
    r"%APPDATA%\npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe")


def main():
    session, jsfile, out = sys.argv[1], sys.argv[2], sys.argv[3]
    js = io.open(jsfile, encoding="utf-8").read()
    p = subprocess.run([EXE, "--session", session, "eval", "--stdin"],
                       input=js.encode("utf-8"), capture_output=True)
    txt = p.stdout.decode("utf-8", "replace").strip()
    if p.returncode != 0:
        txt += "\nSTDERR:" + p.stderr.decode("utf-8", "replace")[:500]
    try:
        v = json.loads(txt)
        while isinstance(v, str):
            v = json.loads(v)
        txt = json.dumps(v, ensure_ascii=False, indent=1)
    except Exception as e:
        txt = "RAW(%s):\n%s" % (e, txt)
    io.open(out, "w", encoding="utf-8").write(txt)
    sys.stderr.write("wrote %s (%d chars)\n" % (out, len(txt)))


if __name__ == "__main__":
    main()
