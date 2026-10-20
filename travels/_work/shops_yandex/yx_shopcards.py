# -*- coding: utf-8 -*-
"""Open the priority Yandex org cards and dump their contacts/social/apps.

usage: python yx_shopcards.py [limit]

cards_input.jsonl (built by parse_rows.py) is read in priority order; each
card is opened through the same throttle dance the fitness pass documented
(re-open after backoff when Yandex answers the "limited" stub, the check
requires this org's id inside the card URL because a failed navigation also
has an <h1>). Raw dumps go to cards/<id>.json — parsed later without
re-hitting the site — and already-dumped ids are skipped, so the run is
resumable across restarts and throttling episodes.
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
SESSION = os.environ.get("YX_SESSION", "yxshop")
PROBE = """(() => JSON.stringify({url: location.href,
  h1: (document.querySelector('h1')||{}).innerText,
  snippets: document.querySelectorAll('li.search-snippet-view').length,
  contact: document.querySelectorAll('[class*="business-contacts-view"]').length,
  text: document.body ? document.body.innerText.slice(0, 40) : null}))()"""


def eval_js(js):
    p = subprocess.run([EXE, "--session", SESSION, "eval", "--stdin"],
                       input=js.encode("utf-8"), capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("eval rc=%s %s" %
                           (p.returncode, p.stderr.decode("utf-8", "replace")[:200]))
    v = json.loads(p.stdout.decode("utf-8", "replace").strip())
    while isinstance(v, str):
        v = json.loads(v)
    return v


def open_url(url):
    subprocess.run([EXE, "--session", SESSION, "open", url], capture_output=True)


def wait_card(url, cid, budget=300):
    started = time.time()
    backoff = 5
    st = None
    while time.time() - started < budget:
        open_url(url)
        for _ in range(12):
            time.sleep(2)
            st = eval_js(PROBE)
            if st.get("h1") and "/maps/org/" in st.get("url", "") and str(cid) in st.get("url", ""):
                return st
        print("   retry %s (%s)" % (url.rstrip("/").split("/")[-2],
                                    json.dumps(st)[:150]), flush=True)
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)
    return None


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    outdir = os.path.join(HERE, "cards")
    os.makedirs(outdir, exist_ok=True)
    js = io.open(os.path.join(HERE, "yx_card2.js"), encoding="utf-8").read()
    recs = [json.loads(l) for l in
            io.open(os.path.join(HERE, "cards_input.jsonl"), encoding="utf-8")
            if l.strip()]
    worked = 0
    for i, r in enumerate(recs, 1):
        cid = r["id"]
        path = os.path.join(outdir, "%s.json" % cid)
        if os.path.exists(path) and os.path.getsize(path) > 100:
            continue
        st = wait_card(r["url"], cid)
        if st is None:
            print("[%d/%d] FAILED %s" % (i, len(recs), r["url"]), flush=True)
            continue
        data = eval_js(js)
        data["list"] = {"name": r["name"], "city": r["city"], "rating": r["rating"],
                        "reviews": r["reviews"], "lon": r["lon"], "lat": r["lat"],
                        "src": r["src"], "priority": r["priority"]}
        io.open(path, "w", encoding="utf-8").write(
            json.dumps(data, ensure_ascii=False, indent=1))
        nlink = sum(1 for l in data.get("msgLinks", []) if l.get("ownOrg"))
        print("[%d/%d] card %s -> own links %d, apps %d, phones %d" %
              (i, len(recs), cid, nlink, len(data.get("apps", [])),
               len(data.get("phones", []))), flush=True)
        worked += 1
        time.sleep(2)
        if limit and worked >= limit:
            break


if __name__ == "__main__":
    main()
