# -*- coding: utf-8 -*-
"""Open each qualifying Yandex Maps org card and dump its contacts/buttons.

usage: python yx_cards.py <in_jsonl> <outdir> [limit]

Same throttle handling as yx_grab: open, poll until the card heading renders,
re-open with backoff if Yandex answers the "limited" stub. The per-card dump is
the raw JSON returned by yx_card.js, written to <outdir>/<id>.json so parsing
can be iterated on without re-hitting the site.
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
SESSION = os.environ.get("YX_SESSION", "yxm")
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
    """Open a card and wait until a real org page is displayed.

    A failed navigation leaves Chrome's own error page, which also has an <h1>
    ("Не удается получить доступ к сайту"), so the check requires the card URL
    to still carry this organisation's id.
    """
    started = time.time()
    backoff = 5
    while time.time() - started < budget:
        open_url(url)
        for _ in range(12):
            time.sleep(2)
            st = eval_js(PROBE)
            if st.get("h1") and "/maps/org/" in st.get("url", "") and cid in st.get("url", ""):
                return st
        print("   retry %s (%s)" % (url.rstrip('/').split('/')[-2],
                                    json.dumps(st)[:150]), flush=True)
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)
    return None


def main():
    src, outdir = sys.argv[1], sys.argv[2]
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    os.makedirs(outdir, exist_ok=True)
    js = io.open(os.path.join(HERE, os.environ.get("YX_CARD_JS", "yx_card2.js")),
                 encoding="utf-8").read()
    recs = [json.loads(l) for l in io.open(src, encoding="utf-8") if l.strip()]
    if limit:
        recs = recs[:limit]
    for i, r in enumerate(recs, 1):
        cid = r["id"]
        path = os.path.join(outdir, cid + ".json")
        if os.path.exists(path):
            print("[%d/%d] skip cached %s" % (i, len(recs), r["name"]), flush=True)
            continue
        st = wait_card(r["url"], cid)
        if st is None:
            print("[%d/%d] FAILED %s" % (i, len(recs), r["url"]), flush=True)
            continue
        data = eval_js(js)
        data["list"] = {"name": r["name"], "rating": r["rating"],
                        "reviews": r["reviews"], "lon": r["lon"], "lat": r["lat"]}
        io.open(path, "w", encoding="utf-8").write(
            json.dumps(data, ensure_ascii=False, indent=1))
        nlink = len(data.get("msgLinks", []))
        print("[%d/%d] card %s -> %s.json (own-org messenger/social links: %d, phones: %d)" %
              (i, len(recs), cid, cid, nlink, len(data.get("phones", []))), flush=True)
        time.sleep(2)


if __name__ == "__main__":
    main()
