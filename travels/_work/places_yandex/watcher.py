# -*- coding: utf-8 -*-
"""Ждёт, пока в places_yandex/rows.jsonl накопится >= THRESHOLD
полезных org/list-строк, затем разово прогоняет merge→blocks→insert→build→commit+push.
Запускается из PowerShell в фоне; логи пишет в watcher.log.
"""
import io
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
YX_ROWS = os.path.join(ROOT, "travels", "_work", "places_yandex", "rows.jsonl")
MERGE_DIR = os.path.join(ROOT, "travels", "_work", "places_merge")
LOG = os.path.join(HERE, "watcher.log")

THRESHOLD = int(sys.argv[1]) if len(sys.argv) > 1 else 30
MAX_HOURS = float(sys.argv[2]) if len(sys.argv) > 2 else 6.0
POLL_SEC = 120


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    # Safe console output under cp866 / misconfigured Windows terminal
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"))


def useful_count():
    if not os.path.exists(YX_ROWS):
        return 0
    n = 0
    for l in io.open(YX_ROWS, encoding="utf-8"):
        l = l.strip()
        if not l:
            continue
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if r.get("kind") in ("org", "list"):
            n += 1
    return n


def run(cmd, cwd=None):
    log("$ " + " ".join(cmd))
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, _ = p.communicate()
    try:
        s = out.decode("utf-8", "replace")
    except Exception:
        s = str(out)
    for line in s.splitlines()[-8:]:
        log("  " + line)
    return p.returncode


def main():
    log("watcher start: threshold=%d poll=%ds max=%.1fh" % (THRESHOLD, POLL_SEC, MAX_HOURS))
    start = time.time()
    last = useful_count()
    log("initial useful=%d" % last)
    while True:
        if time.time() - start > MAX_HOURS * 3600:
            log("ABORT: %d h elapsed, useful=%d < threshold" % (MAX_HOURS, last))
            return 2
        time.sleep(POLL_SEC)
        u = useful_count()
        if u != last:
            log("useful=%d (+%d)" % (u, u - last))
            last = u
        if u >= THRESHOLD:
            log("threshold reached, running pipeline")
            break

    rc = run([sys.executable, "merge_maps.py"], cwd=MERGE_DIR)
    if rc: log("merge FAILED rc=%d" % rc); return rc
    rc = run([sys.executable, "make_blocks.py"], cwd=MERGE_DIR)
    if rc: log("blocks FAILED rc=%d" % rc); return rc
    rc = run([sys.executable, "insert_block.py"], cwd=MERGE_DIR)
    if rc: log("insert FAILED rc=%d" % rc); return rc
    rc = run([sys.executable, "build.py"], cwd=os.path.join(ROOT, "travels", "_work"))
    if rc: log("build FAILED rc=%d" % rc); return rc

    # Stage changed files (avoid passing non-ASCII filenames through PowerShell)
    run(["git", "add", "travels"], cwd=ROOT)
    # Compose commit message
    msg = (
        u"Section 6 top-up: добавлены Яндекс-объекты после троттлинг-паузы\n\n"
        u"Watcher дождался {n}+ полезных org/list-строк в places_yandex/rows.jsonl\n"
        u"(стартовое состояние: 5), затем пере-gенировал merged.jsonl → блоки →\n"
        u"splice в sections/places__*.md → пересобрал Таджикистан.md.\n"
        u"Причина паузы: IP-троттлинг yandex.kz (429/limited body) — браузерный\n"
        u"обход даёт ~1 полезный результат в 2 минуты.\n"
    ).format(n=last)
    msgpath = os.path.join(ROOT, "_commit_msg.txt")
    with io.open(msgpath, "w", encoding="utf-8") as f:
        f.write(msg)
    rc = run(["git", "-c", "i18n.commitEncoding=UTF-8", "commit", "-F", "_commit_msg.txt"], cwd=ROOT)
    if rc: log("commit FAILED rc=%d" % rc); return rc
    rc = run(["git", "push", "origin", "master"], cwd=ROOT)
    log("done. push rc=%d" % rc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
