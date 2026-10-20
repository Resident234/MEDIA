# -*- coding: utf-8 -*-
"""Проставляет конкретные ссылки по решениям linkverify.

Формат маркера: ` [→12](https://…)` — видимый номер = позиция в списке «Обработанные ссылки»,
href = сам URL. Грубые метки `[Т—Ж 2026]`, `[полевой опыт]`, `[aviasales]`, `[onetwotrip]`,
`[tengritravel]` в строке, получившей ссылку, убираются; `[в источниках не найдено]`,
`[не обработано]` и `(мнение автора)` остаются.
"""
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
BUILD = BASE / "build"
SECT = BASE / "sections"
SNAP = BASE / "pre_link_2026-10-13"
WORK = BASE / "linkify_work.json"
DEC = BASE / "linkify_decisions.json"
SHORT_WORK = BASE / "link_short_work.json"
SHORT_RES = BASE / "link_short_result.json"
EXTRA_WORK = BASE / "link_extra_work.json"
EXTRA_RES = BASE / "link_extra_result.json"
LINKS = SECT / "links.md"

COARSE = ("Т—Ж 2026", "полевой опыт", "aviasales", "onetwotrip", "tengritravel")
COARSE_RE = re.compile(r"\s*`\[(?:%s)\]`" % "|".join(re.escape(c) for c in COARSE))
ITEM_RE = re.compile(r"^(\s*)(-\s+|\d+\.\s+)(.*)$")
MARKER_RE = re.compile(r"(?:\s*\[→\d+\]\(https?://[^)]*\))+\s*$")


def link_numbers():
    m = {}
    for ln in LINKS.read_text(encoding="utf-8").splitlines():
        g = re.match(r"^(\d+)\.\s+<(https?://[^>]+)>", ln.strip())
        if g:
            m.setdefault(g.group(2), int(g.group(1)))
    return m


def marker(url, nums):
    n = nums.get(url)
    return " [→%s](%s)" % (n if n else "?", url)


def main():
    apply_only = "--report" in sys.argv
    work = json.loads(WORK.read_text(encoding="utf-8"))
    dec = json.loads(DEC.read_text(encoding="utf-8"))
    nums = link_numbers()
    by_pos = {}
    stats = defaultdict(int)
    for r in work:
        urls = dec.get(str(r["id"]), {}).get("urls") or []
        urls = [u for u in urls if u in nums]
        if urls:
            by_pos[(r["file"], r["line"])] = urls

    # второй и третий проходы: короткие пункты и строки, провалившиеся между порогами длины
    for work_name, res_name in ((SHORT_WORK, SHORT_RES), (EXTRA_WORK, EXTRA_RES)):
        if not work_name.exists():
            continue
        got_all = json.loads(res_name.read_text(encoding="utf-8"))
        for r in json.loads(work_name.read_text(encoding="utf-8")):
            got = got_all.get(str(r["id"]))
            if not got or not got[0]:
                continue
            url, method = got
            if url not in nums:
                print("строка %s:%d — вне списка ссылок: %s" % (r["file"], r["line"], url))
                continue
            by_pos.setdefault((r["file"], r["line"]), [url])
            stats["added_%s" % method] += 1

    # 00_head.md — только легенда и служебные абзацы: проставлять туда ссылки нельзя,
    # матчер цепляется за примеры маркеров и названий меток в тексте пояснений
    skip = ("links.md", "00_head.md")
    files = [f for f in sorted(BUILD.glob("*.md")) + sorted(SECT.glob("*.md"))
             if f.name not in skip]
    new_content = {}
    for f in files:
        rel = f.name
        out_lines = []
        for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            urls = by_pos.get((rel, i))
            if not urls:
                out_lines.append(ln)
                continue
            m = ITEM_RE.match(ln)
            # абзацы прозы (не «- » и не «1. ») тоже могут стоять в решениях — маркер в конец строки
            prefix = (m.group(1) + m.group(2)) if m else ""
            body = (m.group(3) if m else ln)
            had_tag = bool(COARSE_RE.search(body))
            body = MARKER_RE.sub("", COARSE_RE.sub("", body.rstrip()).rstrip()).rstrip()
            tail = "".join(marker(u, nums) for u in urls)
            out_lines.append(prefix + body + tail)
            stats["linked"] += 1
            stats["tag_removed"] += 1 if had_tag else 0
        new_content[f] = "\n".join(out_lines) + "\n"

    def bare(ln):
        return MARKER_RE.sub("", ln.strip())

    total = sum(1 for f in files
                for ln in f.read_text(encoding="utf-8").splitlines()
                if ITEM_RE.match(ln) and len(bare(ln)) >= 27)
    print("строк-пунктов >=27 зн.: %d, строк с маркером после прохода: %d" % (total, stats["linked"]))
    print("грубых меток убрано: %d" % stats["tag_removed"])
    for k, v in sorted(stats.items()):
        if k.startswith("added_"):
            print("   %-34s %d" % (k, v))
    if apply_only:
        miss = [(f.name, i) for f in files for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1)
                if ITEM_RE.match(ln) and len(bare(ln)) >= 27 and (f.name, i) not in by_pos]
        (BASE / "link_unlinked.txt").write_text(
            "\n".join("%s:%d" % p for p in miss) + "\n", encoding="utf-8")
        print("список непрокрытых: link_unlinked.txt (%d)" % len(miss))
        return
    if not SNAP.exists():
        SNAP.mkdir()
        for d in (BUILD, SECT):
            shutil.copytree(d, SNAP / d.name)
    for f, text in new_content.items():
        f.write_text(text, encoding="utf-8")
    print("перезаписано файлов: %d, снапшот: %s" % (len(new_content), SNAP.name))


main()
