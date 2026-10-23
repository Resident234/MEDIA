# -*- coding: utf-8 -*-
"""Обновить раздел «Жильё» одной командой.

Собирает lists/*.jsonl в housing_yx.jsonl, переписывает блок Яндекса в
build/20_zhile.md между его маркерами и пересобирает travel/Таджикистан.md.

usage: python refresh.py [--no-build]
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(HERE)


def run(args, cwd):
    print("> " + " ".join(args))
    return subprocess.call(args, cwd=cwd)


def main():
    args = sys.argv[1:]
    if run([sys.executable, "merge.py"], HERE):
        raise SystemExit("merge failed")
    if run([sys.executable, "mkblock.py"], HERE):
        raise SystemExit("mkblock failed")
    if "--no-build" not in args and run([sys.executable, "build.py"], WORK):
        raise SystemExit("build failed")
    print("done")


if __name__ == "__main__":
    main()
