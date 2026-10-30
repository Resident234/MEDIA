# -*- coding: utf-8 -*-
"""Замеряет числа для легенды в 00_head.md: сколько пунктов-строк и сколько с маркером.

«Пункт-строка» = любая строка собранного файла, начинающуюся с «- » (так же,
как считалось в legend-абзаце до раздела 10). Классификация строк без маркера
`[→N](URL)` детерминированная и идёт списком правил: первое сработавшее правило
и есть категория, поэтому категории не пересекаются.
"""
import io
import re
from pathlib import Path

from docparts import read_all

BASE = Path(__file__).resolve().parent
MARK = re.compile(r"\[→(\d+)\]\((https?://[^)]+)\)")

CATS = [
    ("строки самой легенды", lambda h2, h3, txt: h2 == ""),
    ("строки раздела 10 (источник — карточки 2ГИС, а не статьи)",
     lambda h2, h3, txt: h2.startswith("10.")),
    ("подзаголовки и подводки к спискам", lambda h2, h3, txt: bool(re.search(r"[:*]\s*$", txt))),
    ("задачи из подраздела TODO", lambda h2, h3, txt: (h3 or h2).startswith("TODO")),
    ("строки, где сказано, что факта в источниках нет",
     lambda h2, h3, txt: "Чего в обработанных статьях нет" in (h3 or h2)
     or "[в источниках не найдено]" in txt or "[не обработано]" in txt
     or "не закрыты источниками" in txt or "в обработанных статьях" in txt),
    ("выводы по массиву", lambda h2, h3, txt: "вывод" in txt.lower()),
    ("навигационные строки и пометка о происхождении цен",
     lambda h2, h3, txt: bool(re.search(r"раздел \d|подраздел|см\.|цен", txt))),
]


def main():
    lines = read_all().splitlines()
    h2, h3 = "", ""
    bullets, linked = [], []
    for lineno, raw in enumerate(lines, 1):
        s = raw.strip()
        if s.startswith("### "):
            h3 = s[4:].strip()
            continue
        if s.startswith("## "):
            h2, h3 = s[3:].strip(), ""
            continue
        if s.startswith("# "):
            h2, h3 = "", ""
            continue
        if not s.startswith("- "):
            continue
        body = s[2:]
        bullets.append((lineno, h2, h3, body))
        if MARK.search(body):
            linked.append(lineno)

    linked_keys = set(linked)
    rest = [row for row in bullets if row[0] not in linked_keys]
    counts, leftovers = {}, []
    for lineno, h2row, h3row, body in rest:
        for name, test in CATS:
            if test(h2row, h3row, body):
                counts[name] = counts.get(name, 0) + 1
                break
        else:
            leftovers.append((lineno, h2row, h3row, body))

    report = ["bullets=%d linked=%d pct=%.0f unlinked=%d assigned=%d leftovers=%d" % (
        len(bullets), len(linked_keys), 100.0 * len(linked_keys) / len(bullets),
        len(rest), sum(counts.values()), len(leftovers))]
    for name, _ in CATS:
        report.append("  %-60s %d" % (name, counts.get(name, 0)))
    for lineno, h2row, h3row, body in leftovers:
        report.append("  LEFTOVER L%d [%s / %s] %s" % (lineno, h2row[:24], h3row[:24], body[:140]))
    print("\n".join(report).encode("ascii", "backslashreplace").decode("ascii"))
    with io.open(str(BASE / "legendcount.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(report) + "\n")


if __name__ == "__main__":
    main()
