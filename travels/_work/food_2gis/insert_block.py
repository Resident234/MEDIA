# -*- coding: utf-8 -*-
"""Вставить блок «Заведения: бары, кафе, ...» в build/60_eda.md.

usage: python insert_block.py

Маркеры: `<!-- FOOD_BLOCK_BEGIN -->` / `<!-- FOOD_BLOCK_END -->`. Если они
уже есть в 60_eda.md, содержимое между ними заменяется; если нет — блок
вставляется перед подзаголовком `### Алкоголь и табак`.
"""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "section_7_food_block.md")
DST = os.path.join(HERE, "..", "build", "60_eda.md")
BEGIN = u"<!-- FOOD_BLOCK_BEGIN -->"
END = u"<!-- FOOD_BLOCK_END -->"
ANCHOR = u"\n### Алкоголь и табак"


def main():
    text = io.open(SRC, encoding="utf-8").read().strip()
    body = io.open(DST, encoding="utf-8").read()
    wrapped = BEGIN + u"\n\n" + text + u"\n\n" + END
    b = body.find(BEGIN)
    e = body.find(END)
    if b >= 0 and e >= 0 and e > b:
        new = body[:b] + wrapped + body[e + len(END):]
        action = "replaced"
    else:
        pos = body.find(ANCHOR)
        if pos < 0:
            raise SystemExit("anchor not found: " + ANCHOR.encode("unicode_escape").decode("ascii"))
        new = body[:pos] + u"\n" + wrapped + body[pos:]
        action = "inserted"
    io.open(DST, "w", encoding="utf-8", newline="\n").write(new)
    print("%s, %d bytes -> %s" % (action, len(wrapped),
                                  os.path.relpath(DST, HERE)))


if __name__ == "__main__":
    main()
