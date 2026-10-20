# -*- coding: utf-8 -*-
"""Crawl the 19 2GIS web cards with agent-browser and pull contacts/messengers/hours.

Usage:  python web_crawl.py [limit]
Writes fitness_2gis/web_cards.jsonl (one record per card) and prints ASCII progress.
"""
import io
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SESSION = "tjgym"
ENV = dict(os.environ, AGENT_BROWSER_SESSION=SESSION, PYTHONIOENCODING="utf-8")
JS = io.open(os.path.join(HERE, "extract_card.js"), encoding="utf-8").read()
OUT = os.path.join(HERE, "web_cards.jsonl")


def run(args, timeout=90):
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         env=ENV, cwd=HERE)
    try:
        o, _ = p.communicate(timeout=timeout)
        return p.returncode, o.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        p.kill()
        return 124, "TIMEOUT"


def parse_eval(raw):
    """agent-browser eval prints the JS value; find the JSON object."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    s = m.group(0)
    for cand in (s, s.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8", "replace")):
        try:
            return json.loads(cand)
        except Exception:
            continue
    return None


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 99
    targets = json.load(io.open(os.path.join(HERE, "web_targets.json"), encoding="utf-8"))[:limit]
    done = set()
    if os.path.exists(OUT):
        for line in io.open(OUT, encoding="utf-8"):
            try:
                done.add(json.loads(line)["id"])
            except Exception:
                pass
    fh = io.open(OUT, "a", encoding="utf-8")
    blocked = 0
    for i, t in enumerate(targets):
        if t["id"] in done:
            continue
        rc, out = run(["agent-browser", "open", t["url"]], timeout=90)
        time.sleep(1.5)
        rc2, raw = run(["agent-browser", "eval", JS], timeout=60)
        rec = parse_eval(raw)
        if rec is None:
            rec = {"url": t["url"], "eval_failed": True, "raw": raw[:600]}
        rec["id"] = t["id"]
        rec["name"] = t["name"]
        rec["address"] = t["address"]
        rec["rating"] = t["rating"]
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        cap = bool(rec.get("captcha"))
        phones = len(rec.get("tel", []) or [])
        print("[%02d] %s cap=%d tel=%d wa=%d tg=%d len=%s rc=%d" % (
            i + 1, t["id"][-6:], int(cap), phones,
            len(rec.get("wa", []) or []), len(rec.get("tg", []) or []),
            rec.get("len", -1), rc2))
        blocked = blocked + 1 if cap else 0
        if blocked >= 3:
            print("ABORT: three consecutive captcha pages")
            break
    fh.close()


if __name__ == "__main__":
    main()
