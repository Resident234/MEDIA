# -*- coding: utf-8 -*-
"""Вставить regional_block.md в build/45_svyaz.md сразу после Dushanbe-блока.

usage: python insert_regional.py
Маркеры: TELECOM_REG_BLOCK_BEGIN / TELECOM_REG_BLOCK_END (идемпотентно).
"""
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCK_SRC = os.path.join(HERE, "regional_block.md")
TARGET = os.path.join(HERE, "..", "build", "45_svyaz.md")
BEGIN = u"<!-- TELECOM_REG_BLOCK_BEGIN -->"
END = u"<!-- TELECOM_REG_BLOCK_END -->"
# Вставляем сразу после закрывающего маркера 2GIS-блока.
ANCHOR = u"<!-- TELECOM_BLOCK_END -->"


def main():
    body = io.open(TARGET, encoding="utf-8").read()
    # 1. вырезать старый региональный блок
    pat = re.compile(re.escape(BEGIN) + u"(?s:.)*?" + re.escape(END), re.DOTALL)
    if pat.search(body):
        body = pat.sub(u"", body)
        mode = u"replaced"
    else:
        mode = u"inserted"
    # 2. собрать новый (strip-нуть свои маркеры — добавим заново)
    block = io.open(BLOCK_SRC, encoding="utf-8").read().strip()
    block = re.sub(r"^" + re.escape(BEGIN) + r"\s*|\s*" + re.escape(END) + r"$",
                   u"", block).strip()
    wrapped = u"\n\n%s\n\n%s\n\n%s" % (BEGIN, block, END)
    # 3. анкор — после TELECOM_BLOCK_END
    if ANCHOR not in body:
        raise SystemExit("anchor not found: %s" % ANCHOR)
    body = body.replace(ANCHOR, ANCHOR + wrapped, 1)
    io.open(TARGET, "w", encoding="utf-8", newline="\n").write(body)
    print("target:", os.path.relpath(TARGET, HERE), mode, "bytes:", len(body))


if __name__ == "__main__":
    main()
