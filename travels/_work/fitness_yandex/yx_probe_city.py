# -*- coding: utf-8 -*-
"""Robustly open a Yandex Maps URL in the `yxm` session and report what rendered.

usage: python yx_probe_city.py "<url>" [budget_seconds]

Yandex answers rapid successive navigations with a ~150-byte stub page whose
body is literally "limited". Two things clear it: waiting (exponential backoff)
and taking a detour through the service home page first. This driver applies
both, then dumps an ASCII-safe summary of what actually rendered.
"""
import io
import json
import os
import subprocess
import sys
import time

EXE = os.path.expandvars(
    r"%APPDATA%\npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe")
SESSION = os.environ.get("YX_SESSION", "yxm")
HOME = "https://yandex.kz/maps/"

PROBE = """(() => {
  const sn = [...document.querySelectorAll('li.search-snippet-view')];
  return JSON.stringify({
    url: location.href,
    title: document.title,
    htmlLen: document.documentElement.innerHTML.length,
    snippets: sn.length,
    names: sn.slice(0, 12).map(x => {
      const a = x.querySelector('a.link-overlay');
      return {n: (x.innerText || '').split('\\n')[0].slice(0, 60),
              href: a ? a.getAttribute('href') : null};
    }),
    total: (document.body.innerText.match(/\\d+\\s+(?:результатов|найдено)/) || [null])[0],
    head: document.body ? document.body.innerText.slice(0, 300) : null
  });
})()"""


def ev(js):
    p = subprocess.run([EXE, "--session", SESSION, "eval", "--stdin"],
                       input=js.encode("utf-8"), capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:300])
    v = json.loads(p.stdout.decode("utf-8", "replace").strip())
    while isinstance(v, str):
        v = json.loads(v)
    return v


def op(url):
    subprocess.run([EXE, "--session", SESSION, "open", url], capture_output=True)


def main():
    url = sys.argv[1]
    budget = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    started = time.time()
    backoff = 5
    attempt = 0
    st = None
    while time.time() - started < budget:
        attempt += 1
        if attempt > 1:
            op(HOME)                     # detour resets the "limited" stub
            time.sleep(3)
        op(url)
        for _ in range(10):
            time.sleep(2)
            st = ev(PROBE)
            if st["snippets"] or st["title"]:
                break
        if st["snippets"] or st["title"]:
            print("ready attempt=%d snippets=%d" % (attempt, st["snippets"]), flush=True)
            break
        print("attempt %d stub: htmlLen=%s" % (attempt, st["htmlLen"]), flush=True)
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)
    here = os.path.dirname(os.path.abspath(__file__))
    io.open(os.path.join(here, "_probe_city.json"), "w", encoding="utf-8").write(
        json.dumps(st, ensure_ascii=False, indent=1))
    sys.stdout.buffer.write(json.dumps(st, ensure_ascii=True, indent=1).encode()[:2500])


if __name__ == "__main__":
    main()
