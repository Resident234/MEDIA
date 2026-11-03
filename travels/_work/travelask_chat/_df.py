# -*- coding: utf-8 -*-
"""Сколько сообщений корпуса содержат указанный корень.

Корни читаются из _df_in.txt (по одному в строке): через аргументы командной
строки кириллица в консоли Windows портится кодировкой.

Выход: _df.txt — список df по убыванию.
"""
import io
import os

import _cluster_llm as C

SRC = os.path.join(C.HERE, "_df_in.txt")
OUT = os.path.join(C.HERE, "_df.txt")


def main():
    roots = []
    with io.open(SRC, encoding="utf-8") as f:
        for line in f:
            r = C.norm_text(line.strip())
            if r and r not in roots:
                roots.append(r)
    corpus, _ = C.load_corpus()
    df = dict((r, 0) for r in roots)
    for mid, year, txt, isq, author in corpus:
        for r in roots:
            if r in txt:
                df[r] += 1
    lines = [u"%s: %d" % kv for kv in sorted(df.items(),
                                             key=lambda x: -x[1])]
    io.open(OUT, "w", encoding="utf-8", newline=u"\n").write(
        u"\n".join(lines) + u"\n")
    print("checked %d roots -> %s" % (len(roots), os.path.basename(OUT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
