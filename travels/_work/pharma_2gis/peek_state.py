# -*- coding: utf-8 -*-
"""Посмотреть, в каком виде в HTML выдачи 2ГИС лежат карточки.

usage: python peek_state.py

raw_decode на `"items":[` падает, значит состояние страницы либо экранировано
внутри строки (`\"items\"`), либо маркер вообще не про карточки. Скрипт печатает
сырое окружение маркеров и ищет, где видны id организаций, `address_name` и
`schedule`, чтобы подобрать способ достать JSON.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def pick_file():
    name = None
    for f in sorted(os.listdir(HERE)):
        if f.startswith("_probe_search_") and f.endswith(".html") and \
                os.path.getsize(os.path.join(HERE, f)) > 1000:
            name = f
    return name


def main():
    name = pick_file()
    if not name:
        sys.exit("no probe html")
    body = io.open(os.path.join(HERE, name), encoding="utf-8").read()
    print("file", ascii_(name), "len", len(body))
    for marker in ('"items":[', '\\"items\\":[', "address_name", '"schedule"',
                   '\\"address_name\\"', "working_hours", "/firm/"):
        idxs = [m.start() for m in re.finditer(re.escape(marker), body)]
        print("marker %-20s count=%d first=%s" % (ascii_(marker), len(idxs), idxs[:3]))
    i = body.find("/firm/")
    print("--- ctx around first /firm/ ---")
    print(ascii_(body[max(0, i - 1200):i + 400]))
    j = body.find("address_name")
    print("--- ctx around first address_name ---")
    print(ascii_(body[max(0, j - 700):j + 700]))
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', body, re.S)
    print("script blocks:", len(scripts), "biggest:",
          sorted(len(s) for s in scripts)[-6:])
    for s in scripts:
        if "address_name" in s:
            print("--- state script head ---")
            print(ascii_(s[:500]))
            print("ids inside:", len(set(re.findall(r"/firm/(\d+)", s))))
            break


if __name__ == "__main__":
    main()
