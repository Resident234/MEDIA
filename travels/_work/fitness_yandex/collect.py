# -*- coding: utf-8 -*-
"""Scroll the Yandex Maps result list, collect every rendered item to JSONL.

usage: python collect.py <session> <js_file> <out_jsonl> [max_passes] [stale_stop]

Each pass pipes <js_file> through agent-browser eval --stdin (UTF-8 bytes, so
Cyrillic survives), scrolls the results container one viewport and returns the
currently rendered snippets. Virtualized lists drop off-screen items, so the
union keyed by data-id is accumulated here. Stops after `stale_stop` passes
that add no new ids, or when the container is scrolled to its bottom and two
more passes add nothing, or at max_passes.
"""
import io
import json
import os
import subprocess
import sys
import time

EXE = os.path.expandvars(
    r"%APPDATA%\npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe")


def eval_js(session, js):
    """Run one eval --stdin and return the decoded value."""
    p = subprocess.run([EXE, "--session", session, "eval", "--stdin"],
                       input=js.encode("utf-8"), capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("eval failed rc=%s: %s" %
                           (p.returncode, p.stderr.decode("utf-8", "replace")[:300]))
    txt = p.stdout.decode("utf-8", "replace").strip()
    if not txt:
        raise RuntimeError("eval returned empty stdout")
    v = json.loads(txt)
    while isinstance(v, str):
        v = json.loads(v)
    return v


def main():
    session, jsfile, out = sys.argv[1], sys.argv[2], sys.argv[3]
    max_passes = int(sys.argv[4]) if len(sys.argv) > 4 else 150
    stale_stop = int(sys.argv[5]) if len(sys.argv) > 5 else 4
    delay = float(sys.argv[6]) if len(sys.argv) > 6 else 0.8
    js = io.open(jsfile, encoding="utf-8").read()

    items = {}
    order = []
    stale = 0
    last = None
    for n in range(1, max_passes + 1):
        data = eval_js(session, js)
        new = 0
        for it in data.get("items", []):
            key = it.get("id") or it.get("href")
            if not key:
                continue
            if key not in items:
                items[key] = it
                order.append(key)
                new += 1
            else:
                # keep the richest record seen (some passes render less text)
                old = items[key]
                for f, v in it.items():
                    if (not old.get(f)) and v:
                        old[f] = v
        stale = 0 if new else stale + 1
        at_bottom = data["top"] + data["ch"] >= data["sh"] - 8
        print("pass %3d rendered=%2d new=%d total=%d top=%d/%d(ch %d)%s" %
              (n, data["rendered"], new, len(order), data["top"], data["sh"],
               data["ch"], " BOTTOM" if at_bottom else ""), flush=True)
        last = (data, at_bottom)
        # A virtualized list only renders the window around the scroll offset,
        # so "no new ids" for a couple of passes is normal mid-scroll. Stop only
        # after `stale_stop` dead passes (at the bottom this also gives lazy
        # loading time to append the remaining items).
        if stale >= stale_stop:
            break
        time.sleep(delay)

    with io.open(out, "w", encoding="utf-8", newline="\n") as fh:
        for key in order:
            fh.write(json.dumps(items[key], ensure_ascii=False) + "\n")
    print("wrote %d items -> %s" % (len(order), out))
    print("final: rendered=%d top=%d sh=%d at_bottom=%s" %
          (last[0]["rendered"], last[0]["top"], last[0]["sh"], last[1]))


if __name__ == "__main__":
    main()
