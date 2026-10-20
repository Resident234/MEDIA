# -*- coding: utf-8 -*-
"""Вставить блок «Салоны связи — Душанбе» в build/45_svyaz.md.

usage: python insert_block.py

Идемпотентно: маркеры `<!-- TELECOM_BLOCK_BEGIN -->` / `<!-- TELECOM_BLOCK_END
-->`. Если маркеров ещё нет — дописываем блок в конец файла.
"""
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCK_SRC = os.path.join(HERE, "section_5_block.md")
TARGET = os.path.join(HERE, "..", "build", "45_svyaz.md")
BEGIN = u"<!-- TELECOM_BLOCK_BEGIN -->"
END = u"<!-- TELECOM_BLOCK_END -->"


def main():
    body = io.open(TARGET, encoding="utf-8").read()
    pat = re.compile(re.escape(BEGIN) + u"(?s:.)*?" + re.escape(END), re.DOTALL)
    if pat.search(body):
        body = pat.sub(u"", body)
        mode = u"replaced"
    else:
        mode = u"appended"
    block = io.open(BLOCK_SRC, encoding="utf-8").read().strip()
    # section_5_block.md уже содержит BEGIN/END — вырежем их, чтобы не удвоить.
    block = re.sub(r"^" + re.escape(BEGIN) + r"\s*|\s*" + re.escape(END) + r"$", u"", block).strip()
    wrapped = u"\n\n%s\n\n%s\n\n%s\n" % (BEGIN, block, END)
    body = body.rstrip() + u"\n" + wrapped + u"\n"
    io.open(TARGET, "w", encoding="utf-8", newline="\n").write(body)
    print("target:", os.path.relpath(TARGET, HERE), mode, "bytes:", len(body))


if __name__ == "__main__":
    main()
