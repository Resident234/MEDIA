# -*- coding: utf-8 -*-
"""Итоговое покрытие ссылками: какие пунктов остались без маркера и почему."""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
SKIP = ("links.md", "00_head.md")
ITEM_RE = re.compile(r"^(\s*)(-\s+|\d+\.\s+)(.*)$")
MARKER_RE = re.compile(r"(?:\s*\[→\d+\]\(https?://[^)]*\))+\s*$")
BOLD_ONLY = re.compile(r"^\*\*[^*]+:?\*\*$")
META_RE = re.compile(r"(?:в обработанных (?:статьях|текстах|ссылках)|в статьях (?:нет|не сказано|отсутствует)"
                     r"|не найдено|не приводится|не разбираются|в массив[е ] (?:нет|не входили)"
                     r"|Вывод \(наш|не цитата|ссылки на ваши|В обработанных)")
SHORT_TAG = re.compile(r"`\[(?:Т—Ж 2026|полевой опыт|aviasales|onetwotrip|tengritravel)\]`")

rows = []
total = linked = 0
for f in sorted((BASE / "build").glob("*.md")) + sorted((BASE / "sections").glob("*.md")):
    if f.name in SKIP:
        continue
    for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        m = ITEM_RE.match(ln)
        if not m:
            continue
        body = m.group(3)
        bare = MARKER_RE.sub("", body).rstrip()
        if not bare:
            continue
        total += 1
        if MARKER_RE.search(body):
            linked += 1
            continue
        text = re.sub(r"\*+", "", bare).strip()
        if BOLD_ONLY.match(bare) or text.endswith(":"):
            kind = "подзаголовок/подводка"
        elif META_RE.search(text):
            kind = "пометка «в источниках нет»"
        elif len(text) < 8:
            kind = "служебная"
        elif SHORT_TAG.search(bare):
            kind = "ФАКТ СО СТАРОЙ МЕТКОЙ"
        else:
            kind = "ФАКТ"
        rows.append((kind, f.name, i, len(text), bare))

print("пунктов-строк: %d, с маркером: %d, без: %d" % (total, linked, total - linked))
for kind in ("ФАКТ СО СТАРОЙ МЕТКОЙ", "ФАКТ", "пометка «в источниках нет»",
             "подзаголовок/подводка", "служебная"):
    n = sum(1 for r in rows if r[0] == kind)
    print("  без ссылки — %-26s %d" % (kind, n))
print()
for kind, name, i, L, bare in rows:
    if kind in ("ФАКТ", "ФАКТ СО СТАРОЙ МЕТКОЙ"):
        print("[%s] %s:%d (%d) %s" % (kind[:4], name, i, L, bare[:160]))

