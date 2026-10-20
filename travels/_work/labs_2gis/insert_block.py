# -*- coding: utf-8 -*-
"""Вставить блок «Лаборатории и медицинские анализы» в build/90_med.md.

usage: python insert_block.py

Блок кладём сразу после аптечного (тот вставляет pharma_2gis/insert_block.py)
и перед «### Горная болезнь» — получается последовательность: «Где вообще
лечить» → «Аптеки по всей стране» → «Лаборатории и анализы» → «Горная
болезнь» → «Жара» → «Что отсюда следует».

Идемпотентно по маркерам `<!-- LABS_BLOCK_BEGIN -->` / `<!-- LABS_BLOCK_END -->`.
"""
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCK_SRC = os.path.join(HERE, "section_11_labs_block.md")
TARGET = os.path.join(HERE, "..", "build", "90_med.md")
BEGIN = u"<!-- LABS_BLOCK_BEGIN -->"
END = u"<!-- LABS_BLOCK_END -->"
ANCHOR = u"\n### \u0413\u043e\u0440\u043d\u0430\u044f \u0431\u043e\u043b\u0435\u0437\u043d\u044c"


def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def main():
    body = io.open(TARGET, encoding="utf-8").read()
    pat = re.compile(re.escape(BEGIN) + u"(?s:.)*?" + re.escape(END),
                     re.DOTALL)
    body = pat.sub(u"", body)
    block = io.open(BLOCK_SRC, encoding="utf-8").read().strip()
    wrapped = u"\n\n%s\n\n%s\n\n%s\n" % (BEGIN, block, END)
    if ANCHOR not in body:
        raise SystemExit("anchor not found: %s" % a(ANCHOR))
    body = body.replace(ANCHOR, wrapped.rstrip() + ANCHOR, 1)
    io.open(TARGET, "w", encoding="utf-8", newline="\n").write(body)
    print("target:", os.path.relpath(TARGET, HERE), "bytes:", len(body))


if __name__ == "__main__":
    main()
