# -*- coding: utf-8 -*-
"""Замер качества атрибуции по частям сборки (без правки файлов)."""
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from linklib import Index, link_numbers, toks  # noqa: E402

BASE = Path(__file__).resolve().parent
BUILD = BASE / "build"
SECT = BASE / "sections"

SKIP_FILES = {"links.md"}
TAG_RE = re.compile(r"`\[([^\]]+)\]`")


def target_lines():
    files = sorted(BUILD.glob("*.md")) + sorted(SECT.glob("*.md"))
    for f in files:
        if f.name in SKIP_FILES:
            continue
        for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            t = ln.strip()
            if not t.startswith("- "):
                continue
            body = t[2:]
            if len(body) < 25:
                continue
            if re.match(r"^\d+\.\s*<https?://", body):
                continue
            yield f.name, i, body, TAG_RE.findall(body)


def main():
    idx = Index()
    idx.finish_idf()
    nums = link_numbers()
    print("units=%d sources=%d doc_urls=%d" % (idx.n_units, len(idx.notes), len(nums)),
          file=sys.stderr)
    hist = defaultdict(int)
    rows = []
    for fname, lineno, body, tags in target_lines():
        q = set(toks(body))
        if len(q) < 2:
            hist["too_few"] += 1
            continue
        cand = idx.best_for(q)
        if not cand:
            hist["no_match"] += 1
            rows.append((fname, lineno, body, tags, cand))
            continue
        best = cand[0][1]
        second = cand[1][1] if len(cand) > 1 else 0.0
        gap = best - second
        b = "hi" if best >= 0.60 else ("mid" if best >= 0.42 else "lo")
        if gap < 0.04:
            b += "-tie"
        hist[b] += 1
        rows.append((fname, lineno, body, tags, cand))
    print(dict(sorted(hist.items())), file=sys.stderr)
    out = []
    for fname, lineno, body, tags, cand in rows:
        top = cand[0] if cand else None
        out.append("%s:%d b=%s gap=%.3f tags=%s\n   %s\n   -> %s | %s | %s" % (
            fname, lineno, ("%.2f" % top[1]) if top else "none",
            (top[1] - (cand[1][1] if len(cand) > 1 else 0.0)) if top else 0.0,
            ",".join(tags)[:40], body[:110],
            ("#" + str(nums.get(top[0], "?")) + " " + top[0]) if top else "-",
            top[2] if top else "-", (top[3][:100] if top else "-")))
    (BASE / "link_measure.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("wrote link_measure.txt rows=%d" % len(out), file=sys.stderr)
    lo = [r for r in rows if r[4] and r[4][0][1] < 0.42]
    print("low-score rows: %d" % len(lo), file=sys.stderr)
    for fname, lineno, body, tags, cand in lo[:8]:
        print("  %s:%d %s\n     -> %s (%.2f)" % (fname, lineno, body[:80], cand[0][0], cand[0][1]),
              file=sys.stderr)


main()
