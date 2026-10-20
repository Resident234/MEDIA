# -*- coding: utf-8 -*-
"""Run one agent-browser command in the yxm session, dump stdout to a file.

usage: python yx_run.py <outfile> <args...>
Output is written as raw UTF-8 to <outfile> so Cyrillic survives PowerShell.
"""
import os
import subprocess
import sys

EXE = os.path.expandvars(
    r"%APPDATA%\npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe")


def main():
    out = sys.argv[1]
    args = sys.argv[2:]
    p = subprocess.run([EXE] + args, capture_output=True)
    with open(out, "wb") as fh:
        fh.write(p.stdout)
        fh.write(b"\n---STDERR---\n")
        fh.write(p.stderr)
    sys.stderr.write("rc=%d bytes=%d\n" % (p.returncode, len(p.stdout)))
    return p.returncode


if __name__ == "__main__":
    sys.exit(main())
