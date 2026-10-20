# -*- coding: utf-8 -*-
"""Вставить banks_block.md (Душанбе) и khujand_block.md (Худжанд) в
build/30_dengi.md. Идемпотентно по парам маркеров.

usage: python insert_block.py
"""
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "..", "build", "30_dengi.md")

BLOCKS = [
    (u"BANKS_DUS", os.path.join(HERE, "banks_block.md")),
    (u"BANKS_KHJ", os.path.join(HERE, "khujand_block.md")),
]


def strip_markers(content, begin, end):
    return re.sub(r"^" + re.escape(begin) + r"\s*|\s*" + re.escape(end) + r"$",
                  u"", content).strip()


def splice(body, name, block_content):
    begin = u"<!-- %s_BEGIN -->" % name
    end = u"<!-- %s_END -->" % name
    pat = re.compile(re.escape(begin) + u"(?s:.)*?" + re.escape(end), re.DOTALL)
    block = strip_markers(block_content, begin, end)
    wrapped = u"\n\n%s\n\n%s\n\n%s\n" % (begin, block, end)
    if pat.search(body):
        new_body = pat.sub(lambda m: wrapped, body)
        return new_body, u"replaced"
    # Иначе — вставить перед "### Чего в обработанных статьях нет" или
    # после "### TODO: опросить банки" (в самом конце файла).
    anchor2 = u"### TODO: опросить банки Душанбе и Худжанда"
    if anchor2 in body:
        # ищем последнюю пустую строку после заголовка TODO-секции и
        # добавляем блок в конец.
        idx = body.find(anchor2)
        nxt = body.find(u"\n###", idx + len(anchor2))
        if nxt < 0:
            nxt = len(body)
        return body[:nxt] + wrapped + body[nxt:], u"appended-after-TODO"
    return body.rstrip() + wrapped, u"appended-end"


def main():
    body = io.open(TARGET, encoding="utf-8").read()
    for name, path in BLOCKS:
        if not os.path.exists(path):
            print("skip (missing):", path)
            continue
        content = io.open(path, encoding="utf-8").read()
        body, mode = splice(body, name, content)
        print("%s: %s (%d bytes block)" % (name, mode, len(content)))
    io.open(TARGET, "w", encoding="utf-8", newline="\n").write(body)
    print("target:", os.path.relpath(TARGET, HERE), "total bytes:", len(body))


if __name__ == "__main__":
    main()
