# -*- coding: utf-8 -*-
"""Держит добор жилья запущенным, пока не кончатся круги или попытки.

run_lists.py сам переживает сбои отдельных запросов, но если процесс умрёт
целиком (браузер, исключение в CLI), без присмотра сбор просто встанет.
Супервизор перезапускает его с паузой и пишет всё в lists/supervisor.log;
файлы lists/*.jsonl и маркеры .ok делают перезапуск продолжением, а не
началом заново.

usage: python supervise.py [--rounds 10] [--max-restarts 6]
"""
import io
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LISTS = os.path.join(HERE, "lists")
LOG = os.path.join(LISTS, "supervisor.log")
PAUSE = 300


def log(msg):
    line = "[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    sys.stdout.buffer.write(line.encode("ascii", "backslashreplace"))
    sys.stdout.buffer.flush()
    io.open(LOG, "a", encoding="utf-8").write(line)


def main():
    os.makedirs(LISTS, exist_ok=True)
    rounds, restarts = 10, 6
    args, i = sys.argv[1:], 0
    while i < len(args):
        if args[i] == "--rounds" and i + 1 < len(args):
            rounds, i = int(args[i + 1]), i + 2
        elif args[i] == "--max-restarts" and i + 1 < len(args):
            restarts, i = int(args[i + 1]), i + 2
        else:
            i += 1
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    for attempt in range(1, restarts + 1):
        log("start attempt %d/%d (rounds=%d)" % (attempt, restarts, rounds))
        rc = subprocess.call([sys.executable, "-u", "run_lists.py",
                              "--rounds", str(rounds)], cwd=HERE, env=env)
        log("run_lists exited rc=%d" % rc)
        if rc == 0:
            log("rounds finished, nothing to retry; stop")
            return
        if attempt < restarts:
            log("restart in %ds" % PAUSE)
            time.sleep(PAUSE)
    log("gave up after %d attempts" % restarts)


if __name__ == "__main__":
    main()
