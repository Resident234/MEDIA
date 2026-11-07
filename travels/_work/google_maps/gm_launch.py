# -*- coding: utf-8 -*-
"""Sequential supervisor: runs every domain's collector one after another.

Because all collectors share the single `ggm` agent-browser session, they must
run serially (parallel would fight over the browser and get Google to throttle
us harder). This script is intended to be launched as a detached background
process (Start-Process -WindowStyle Hidden) and left running for days.

For each domain it:
  1. Runs `run_domain.py plans/<dom>.tsv out/<dom>` in --lists-only mode
     first, so every search URL is harvested and every unique place lands in
     `out/<dom>/rows.jsonl`. This is the "find all cards" phase.
  2. Then runs the same in --cards-only mode: opens every harvested place
     page and extracts phone/site/hours/etc. This is the "visit every card"
     phase the user opted into.
  3. Both phases are resumable via `.ok` markers and `cards/<fid>.json` cache
     files, so a rerun after a crash or reboot picks up where it stopped.
  4. `out/<dom>.done` is written ONLY when the domain is actually complete:
     every planned (city, query) row has its `.ok` and every row in
     `rows.jsonl` has its card JSON. A `FAIL no-harvest` search leaves its
     `.ok` absent, so stamping unconditionally would freeze that gap forever
     (the stamp makes the next pass SKIP the whole domain). Incomplete
     domains are logged and retried on the next run instead.

Log lines go to `out/supervisor.log` alongside per-domain stdout/stderr
redirects. To stop the whole pipeline: kill the python.exe PID written into
`out/supervisor.pid`, or `python gm_launch.py --stop`.
"""
import argparse
import io
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLANS = os.path.join(HERE, "plans")
OUT = os.path.join(HERE, "out")
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import run_domain

# Small domains first so the useful pilot data lands earliest; big domains
# last so we can kill the run at any point and still splice the smaller ones.
DOMAINS = [
    "fitness", "banks", "housing", "shops", "telecom",
    "labs", "pharma", "food",
]


def domain_stamp(name):
    return os.path.join(OUT, "%s.done" % name)


def missing_searches(plan_path, outdir):
    """Planned (slug, query) rows whose `.ok` marker is still absent.

    A search that hit a captcha / bot-wall and never harvested leaves no `.ok`
    (`FAIL no-harvest` path in run_domain), so this is the completeness probe
    for the lists phase.
    """
    out = []
    for slug, _near, q in run_domain.load_plan(plan_path):
        ok = os.path.join(outdir, "%s__%s.ok" % (slug, run_domain.slugify(q)))
        if not os.path.exists(ok):
            out.append((slug, q))
    return out


def missing_cards(outdir):
    """Harvested fids that have no cached card JSON yet."""
    cards_dir = os.path.join(outdir, "cards")
    rows = run_domain.read_rows(os.path.join(outdir, "rows.jsonl"))
    out = []
    for r in rows.values():
        fid = r.get("fid")
        if not fid:
            continue
        if not os.path.exists(os.path.join(cards_dir,
                                           run_domain.slugify(fid) + ".json")):
            out.append(fid)
    return out


def run_phase(cmd, out_log, err_log):
    """Run cmd, streaming stdout to out_log and stderr to err_log. Blocks."""
    # Belt-and-suspenders: the child also reconfigures its own stdio, but
    # forcing UTF-8 env keeps the console echo from crashing on cp866/cp1251
    # before that reconfigure runs. `-X utf8` alone proved insufficient once
    # stdout is a redirected pipe.
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    with io.open(out_log, "a", encoding="utf-8", newline="\n") as o, \
         io.open(err_log, "a", encoding="utf-8", newline="\n") as e:
        e.write("\n===== %s =====\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        e.flush()
        p = subprocess.Popen(cmd, stdout=o, stderr=e, env=env)
        rc = p.wait()
        e.write("===== exit rc=%d =====\n" % rc)
        e.flush()
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", nargs="*", default=None,
                    help="subset of domain names to run (default: all)")
    ap.add_argument("--stop", action="store_true",
                    help="kill the running supervisor via out/supervisor.pid")
    ap.add_argument("--lists-only", action="store_true")
    ap.add_argument("--cards-only", action="store_true")
    ap.add_argument("--rest-between", type=int, default=60,
                    help="seconds to sleep between domains (anti-throttle)")
    args = ap.parse_args()

    if args.stop:
        pid_path = os.path.join(OUT, "supervisor.pid")
        if os.path.exists(pid_path):
            pid = int(io.open(pid_path).read().strip())
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               check=False)
                print("killed supervisor pid", pid)
            finally:
                os.remove(pid_path)
        return

    os.makedirs(OUT, exist_ok=True)
    io.open(os.path.join(OUT, "supervisor.pid"), "w").write(str(os.getpid()))

    wanted = args.domains or DOMAINS
    sup = os.path.join(OUT, "supervisor.log")
    for dom in wanted:
        plan = os.path.join(PLANS, dom + ".tsv")
        outdir = os.path.join(OUT, dom)
        os.makedirs(outdir, exist_ok=True)
        if not os.path.exists(plan):
            _log(sup, "[%s] SKIP missing plan: %s" % (dom, plan))
            continue
        stamp = domain_stamp(dom)
        if os.path.exists(stamp):
            _log(sup, "[%s] SKIP already completed" % dom)
            continue
        out_log = os.path.join(OUT, "%s.out" % dom)
        err_log = os.path.join(OUT, "%s.err" % dom)
        base = [sys.executable, "-X", "utf8",
                os.path.join(HERE, "run_domain.py"), plan, outdir]
        _log(sup, "[%s] === START ===" % dom)
        if not args.cards_only:
            rc = run_phase(base + ["--lists-only"], out_log, err_log)
            _log(sup, "[%s] lists phase rc=%d" % (dom, rc))
            # Once every planned (city, query) search has its .ok, publish the
            # name+map-link section into the guide and commit+push it. This runs
            # BEFORE the long cards phase so the category lands early; publishing
            # only needs rows.jsonl. Wrapped so a git/IO hiccup can never kill
            # the multi-day collection.
            if not missing_searches(plan, outdir):
                try:
                    import gm_publish
                    _log(sup, "[%s] PUBLISH: %s" %
                         (dom, gm_publish.publish_domain(dom)))
                except Exception as ex:
                    _log(sup, "[%s] PUBLISH-FAIL: %r" % (dom, ex))
            else:
                _log(sup, "[%s] publish skipped: lists incomplete" % dom)
        if not args.lists_only:
            rc = run_phase(base + ["--cards-only"], out_log, err_log)
            _log(sup, "[%s] cards phase rc=%d" % (dom, rc))
        gaps = missing_searches(plan, outdir)
        pending = missing_cards(outdir)
        if gaps or pending:
            # No stamp: the next `python gm_launch.py` re-enters this domain
            # and retries exactly these rows (everything else skips on `.ok`).
            _log(sup, "[%s] INCOMPLETE: %d searches without .ok, "
                      "%d places without card JSON -> no .done stamp" %
                 (dom, len(gaps), len(pending)))
            for slug, q in gaps[:10]:
                _log(sup, "[%s]   missing .ok: %s / %s" % (dom, slug, q))
            for fid in pending[:10]:
                _log(sup, "[%s]   missing card: %s" % (dom, fid[:24]))
        else:
            with io.open(stamp, "w", encoding="utf-8") as fh:
                fh.write(time.strftime("%Y-%m-%d %H:%M:%S\n"))
            _log(sup, "[%s] === DONE ===" % dom)
        time.sleep(args.rest_between)
    _log(sup, "SUPERVISOR EXITED")
    try:
        os.remove(os.path.join(OUT, "supervisor.pid"))
    except OSError:
        pass


def _log(path, msg):
    line = "%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    with io.open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line)
    sys.stdout.buffer.write(line.encode("utf-8", "replace"))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
