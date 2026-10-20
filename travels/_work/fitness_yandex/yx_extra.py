# -*- coding: utf-8 -*-
"""Second pass over the qualifying cards: the "Подробнее об организации" tab and
the organisation's own website, looking for WhatsApp / Telegram links.

usage: python yx_extra.py <final_jsonl> <outdir>

Yandex cards expose messengers only when the owner added them; the details tab
and the listed website are the two places where the same contact can still be
published. Anything found here is stored per source so the guide can say where
a link came from instead of blending channels together.
"""
import io
import json
import os
import re
import subprocess
import sys
import time

EXE = os.path.expandvars(
    r"%APPDATA%\npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe")
HERE = os.path.dirname(os.path.abspath(__file__))
SESSION = os.environ.get("YX_SESSION", "yxm")
JS = io.open(os.path.join(HERE, "yx_extra.js"), encoding="utf-8").read()
READY = """(() => JSON.stringify({url: location.href,
  anchors: document.querySelectorAll('a[href]').length,
  len: document.body ? document.body.innerText.length : 0}))()"""


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


def visit(url, marker, budget=150):
    """Open url and wait until the page looks real (host stays the expected one)."""
    started = time.time()
    backoff = 5
    while time.time() - started < budget:
        open_url(url)
        for _ in range(10):
            time.sleep(2)
            st = eval_js(READY)
            cur = st.get("url", "")
            if cur.startswith("chrome-error"):
                continue
            if marker in cur and st.get("anchors", 0) > 5:
                return eval_js(JS)
        print("   retry %s (%s)" % (url[:70], json.dumps(st)[:130]), flush=True)
        time.sleep(backoff)
        backoff = min(backoff * 2, 45)
    return None


def main():
    src, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    recs = [json.loads(l) for l in io.open(src, encoding="utf-8") if l.strip()]
    seen_sites = set()
    for i, r in enumerate(recs, 1):
        cid = r["id"]
        fpath = os.path.join(outdir, cid + "_features.json")
        if not os.path.exists(fpath):
            d = visit(r["url"] + "?tab=features", cid)
            if d is None:
                print("[%d/%d] features FAILED %s" % (i, len(recs), cid), flush=True)
            else:
                io.open(fpath, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=1))
                print("[%d/%d] features %s: wa=%s tg=%s msglinks=%d" %
                      (i, len(recs), cid, d["bodyHas"]["whatsapp"],
                       d["bodyHas"]["telegram"], len(d["msgLinks"])), flush=True)
            time.sleep(2)
        site = r.get("site")
        if site:
            host = re.sub(r"^https?://", "", site).rstrip("/")
            if host not in seen_sites:
                seen_sites.add(host)
                spath = os.path.join(outdir, "site_" + re.sub(r"\W+", "_", host) + ".json")
                if not os.path.exists(spath):
                    # many sites redirect www.<host> -> <host>, so match on the
                    # bare hostname without the www prefix
                    marker = host.split("/")[0]
                    marker = re.sub(r"^www\.", "", marker)
                    d = visit(site, marker, budget=90)
                    if d is None:
                        print("[%d/%d] site FAILED %s" % (i, len(recs), host), flush=True)
                    else:
                        io.open(spath, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=1))
                        print("[%d/%d] site %s: wa=%s tg=%s msglinks=%d phones=%d" %
                              (i, len(recs), host, d["bodyHas"]["whatsapp"],
                               d["bodyHas"]["telegram"], len(d["msgLinks"]),
                               len(d["phones"])), flush=True)
                    time.sleep(2)


if __name__ == "__main__":
    main()
