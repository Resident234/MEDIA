# -*- coding: utf-8 -*-
"""Дамп размеченных сообщений по метке: python _deliv_dump.py [МЕТКА ...]

Без аргументов — все метки. Пишет _deliv_dump.txt в UTF-8 (консоль cp866
не печатает кириллицу). Нужен, чтобы глазами проверить точность разметки.
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAND = os.path.join(HERE, "_deliv_cand.jsonl")
LAB = os.path.join(HERE, "_deliv_labels.jsonl")
OUT = os.path.join(HERE, "_deliv_dump.txt")


def main():
    want = set(x.upper() for x in sys.argv[1:])
    labels = {}
    for line in io.open(LAB, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        labels[r["id"]] = r["label"]
    out = []
    cnt = {}
    for line in io.open(CAND, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        lab = labels.get(r["id"])
        if lab is None:
            continue
        cnt[lab] = cnt.get(lab, 0) + 1
        if want and lab not in want:
            continue
        t = re.sub(r"\s+", u" ", r.get("text") or u"")[:230]
        rt = re.sub(r"\s+", u" ", r.get("reply_text") or u"")[:110]
        out.append(u"%s #%s %s | %s%s" % (
            lab, r["id"], (r.get("date") or u"")[:10], t,
            (u" >> ответ на: " + rt) if rt else u""))
    io.open(OUT, "w", encoding="utf-8", newline=u"\n").write(
        u"\n".join(out) + u"\n")
    print("labeled=%d rows=%d -> %s" % (sum(cnt.values()), len(out),
                                         os.path.basename(OUT)))
    print(", ".join(u"%s=%d" % kv for kv in sorted(cnt.items())))


if __name__ == "__main__":
    main()
