# -*- coding: utf-8 -*-
"""Navigate to a Yandex Maps search and scroll-collect the whole result list.

usage: python yx_grab.py <qline> <out_jsonl> [max_passes] [stale_stop] [delay]

Yandex throttles repeated navigations with a stub page whose body is literally
"limited"; a fresh navigation after a backoff clears it. So this driver:
  1. opens the search URL for line <qline> of _q.txt,
  2. polls until the results container exists and snippets are rendered
     (re-opening with exponential backoff when the stub page comes back),
  3. rewinds the container and scrolls one viewport per pass, accumulating the
     union of rendered snippets keyed by data-id (list is virtualized).
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
# City catalog can be swapped for the coverage probe via YX_BASE.
BASE = os.environ.get("YX_BASE") or (
    "https://yandex.kz/maps/10318/dushanbe/search/{q}/"
    "?ll=68.787000%2C38.559800&sll=68.787000%2C38.559800&z=12")
PROBE = """(() => JSON.stringify({url: location.href,
  snippets: document.querySelectorAll('li.search-snippet-view').length,
  scroll: document.querySelectorAll('.scroll__container').length,
  text: document.body ? document.body.innerText.slice(0, 60) : null}))()"""


def run(args, stdin=None):
    return subprocess.run([EXE] + args, input=stdin, capture_output=True)


def eval_js(session, js):
    p = run(["--session", session, "eval", "--stdin"], js.encode("utf-8"))
    if p.returncode != 0:
        raise RuntimeError("eval rc=%s %s" %
                           (p.returncode, p.stderr.decode("utf-8", "replace")[:200]))
    v = json.loads(p.stdout.decode("utf-8", "replace").strip())
    while isinstance(v, str):
        v = json.loads(v)
    return v


def open_url(session, url):
    run(["--session", session, "open", url])


def wait_ready(session, url, budget=240):
    """Open the search URL and wait for a rendered list, retrying on throttle."""
    started = time.time()
    backoff = 5
    attempt = 0
    while time.time() - started < budget:
        attempt += 1
        if attempt > 1:
            # A detour through the service home page is what actually clears
            # the "limited" stub; re-opening the same URL back-to-back does not.
            run(["--session", session, "open",
                 "https://yandex.kz/maps/"])
            time.sleep(3)
        open_url(session, url)
        for _ in range(12):
            time.sleep(2)
            st = eval_js(session, PROBE)
            if st["scroll"] and st["snippets"]:
                print("ready after %d attempt(s): snippets=%d url=%s" %
                      (attempt, st["snippets"], st["url"][:110]), flush=True)
                return st
        print("attempt %d not ready: %s" % (attempt, json.dumps(st)[:220]),
              flush=True)
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)
    raise RuntimeError("list never became ready")


def main():
    qline = sys.argv[1]
    out = sys.argv[2]
    max_passes = int(sys.argv[3]) if len(sys.argv) > 3 else 200
    stale_stop = int(sys.argv[4]) if len(sys.argv) > 4 else 5
    delay = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0
    session = os.environ.get("YX_SESSION", "yxm")

    q = io.open(os.path.join(HERE, "_q.txt"), encoding="utf-8").read().splitlines()[int(qline) - 1].strip()
    url = BASE.format(q=q)
    wait_ready(session, url)

    js = io.open(os.path.join(HERE, "yx_collect2.js"), encoding="utf-8").read()
    items, order, stale = {}, [], 0
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
