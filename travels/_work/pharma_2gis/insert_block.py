# -*- coding: utf-8 -*-
"""Вставить блок «Аптеки по всей стране» в build/90_med.md.

usage: python insert_block.py

Блок лежит в `pharma_2gis/section_11_block.md` (его собирает make_md.py из
данных 2ГИС-выдачи + карточек). Вставка — между существующими
подсекциями «### Где вообще лечить» и «### Горная болезнь»: аптеки
логичнее всего смотрятся сразу после общего абзаца про «где лечить» и
до блоков про горную болезнь/жежду/санатории.

Идемпотентно: перед вставкой вырезается предыдущая версия блока по
маркерам `<!-- PHARMACY_BLOCK_BEGIN -->` / `<!-- PHARMACY_BLOCK_END -->`.
"""
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCK_SRC = os.path.join(HERE, "section_11_block.md")
TARGET = os.path.join(HERE, "..", "build", "90_med.md")
BEGIN = u"<!-- PHARMACY_BLOCK_BEGIN -->"
END = u"<!-- PHARMACY_BLOCK_END -->"
# Вставляем после абзаца «### Где вообще лечить», перед «### Горная болезнь».
ANCHOR = u"\n### \u0413\u043e\u0440\u043d\u0430\u044f \u0431\u043e\u043b\u0435\u0437\u043d\u044c"
# Аптечный блок идёт ПЕРЕД лабораторным (тот вставляет labs_2gis/insert_block.py
# и тоже цепляется за «Горную болезнь»): если лаборатории уже на месте,
# встаём перед их маркером, иначе порядок зависит от порядка запуска скриптов.
LABS_ANCHOR = u"\n<!-- LABS_BLOCK_BEGIN -->"


def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def main():
    body = io.open(TARGET, encoding="utf-8").read()
    # 1. вырезать старый блок, если был
    pat = re.compile(re.escape(BEGIN) + u"(?s:.)*?" + re.escape(END),
                     re.DOTALL)
    body = pat.sub(u"", body)
    # 2. собрать новый
    block = io.open(BLOCK_SRC, encoding="utf-8").read().strip()
    wrapped = u"\n\n%s\n\n%s\n\n%s\n" % (BEGIN, block, END)
    # 3. вставить по анкеру
    anchor = LABS_ANCHOR if LABS_ANCHOR in body else ANCHOR
    if anchor not in body:
        raise SystemExit("anchor not found: %s" % a(ANCHOR))
    body = body.replace(anchor, wrapped.rstrip() + anchor, 1)
    io.open(TARGET, "w", encoding="utf-8", newline="\n").write(body)
    print("target:", os.path.relpath(TARGET, HERE), "bytes:", len(body))


if __name__ == "__main__":
    main()
