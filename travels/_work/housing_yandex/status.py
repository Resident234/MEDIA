# -*- coding: utf-8 -*-
"""Сводка переписи: что уже собрано, что ещё нет.

usage: python status.py [--tail 8]

Печатает таблицу по населённым пунктам (объектов, сколько запросов закрыто,
помечен ли как ретранслятор), итог по уникальным id и хвост run.log.
Только читает файлы — браузер не трогает, сбору не мешает.
"""
import glob
import io
import json
import os
import sys

import run_lists as R

HERE = os.path.dirname(os.path.abspath(__file__))
LISTS = os.path.join(HERE, "lists")


def main():
    tail = 8
    args = sys.argv[1:]
    if "--tail" in args:
        tail = int(args[args.index("--tail") + 1])
    ids, rows = {}, 0
    for path in glob.glob(os.path.join(LISTS, "*.jsonl")):
        for line in io.open(path, encoding="utf-8"):
            try:
                it = json.loads(line)
            except ValueError:
                continue
            rows += 1
            ids[it.get("id") or it.get("title")] = 1
    print("rows=%d uniq=%d towns=%d" % (rows, len(ids), len(R.CITIES)))
    for town in R.rows(None):
        files = sorted(glob.glob(os.path.join(
            LISTS, "%s__*.jsonl" % town["key"])))
        n = 0
        for f in files:
            n += len(R.load_items(f))
        oks = len(glob.glob(os.path.join(
            LISTS, "%s__*.jsonl.ok" % town["key"])))
        relay = os.path.exists(os.path.join(
            LISTS, "%s__town.relay" % town["key"]))
        if not files and not relay:
            continue
        print("  %-14s items=%-4d ok=%d/%d%s" % (
            town["key"], n, oks, len(R.QUERIES),
            "  RELAY" if relay else ""))
    log = os.path.join(LISTS, "run.log")
    if os.path.exists(log):
        lines = io.open(log, encoding="utf-8").readlines()[-tail:]
        print("--- run.log tail")
        for line in lines:
            print("  " + line.rstrip().encode(
                "ascii", "backslashreplace").decode("ascii"))


if __name__ == "__main__":
    main()
