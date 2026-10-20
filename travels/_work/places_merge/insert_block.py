# -*- coding: utf-8 -*-
"""Вставить каждый блок blocks/<stem>__map_block.md в sections/<stem>.md.

usage: python insert_block.py

Идемпотентно: в целевом файщем ищем маркеры `<!-- PLACES_MAP_BLOCK_BEGIN -->`
/ `<!-- PLACES_MAP_BLOCK_END -->`. Если они есть — заменяем между ними;
если их нет — дописываем блок в конец файла (перед пустой последней
строкой, если она есть).
"""
import glob
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCKS = os.path.join(HERE, "blocks")
SECTIONS = os.path.join(HERE, "..", "sections")

BEGIN = u"<!-- PLACES_MAP_BLOCK_BEGIN -->"
END = u"<!-- PLACES_MAP_BLOCK_END -->"


def splice(target, block_text):
    body = io.open(target, encoding="utf-8").read()
    b = body.find(BEGIN)
    e = body.find(END)
    if b >= 0 and e >= 0 and e > b:
        new = body[:b] + block_text.strip() + body[e + len(END):]
        action = "replaced"
    else:
        if not body.endswith("\n"):
            body += "\n"
        new = body + block_text
        action = "appended"
    io.open(target, "w", encoding="utf-8", newline="\n").write(new)
    return action, len(block_text)


def main():
    done = 0
    for path in sorted(glob.glob(os.path.join(BLOCKS, "*.md"))):
        stem = os.path.basename(path).replace(u"__map_block.md", u"")
        target = os.path.join(SECTIONS, stem + u".md")
        if not os.path.exists(target):
            print("MISS:", stem)
            continue
        block_text = io.open(path, encoding="utf-8").read()
        act, sz = splice(target, block_text)
        print("%-70s %s (%d bytes)" % (stem[:70], act, sz))
        done += 1
    print("inserted:", done)


if __name__ == "__main__":
    main()
