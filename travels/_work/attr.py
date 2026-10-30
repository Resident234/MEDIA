# -*- coding: utf-8 -*-
"""Атрибуция предложений итогового файла к URL-источникам из notes/*.md.

Индекс: каждая строка-факт из notes/<src>.md знает свой URL (первая строка "# <url>").
Для строки документа считаем lexical containment по всем строкам индекса и отдаём
топ-3 источника. Только отчёт, ничего не правит.
"""
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

from docparts import read_all

BASE = Path(__file__).resolve().parent
NOTES = BASE / "notes"

STOP = set("""и во с на как что это для от до из по при все уже ещё не ни он она они его её мы вы ты
такой такой был была были есть был очень один одна самой сам так но или ли же то тех этих тем этим
том что чем какой какие мой наша наш его их более менее который которая которые быть стало стал
стала надо нужно можно нельзя всего всех всем всю всей прям вообще просто действительно""".split())

TAG_RE = re.compile(r"`\[[^\]]*\]`|\(мнение автора[^)]*\)|`[^`]*`")
WORD_RE = re.compile(r"[а-яё0-9]+")


def norm(s):
    s = s.lower().replace("ё", "е")
    s = TAG_RE.sub(" ", s)
    return s


def toks(s):
    out = []
    for w in WORD_RE.findall(norm(s)):
        if w.isdigit():
            out.append(w)
        elif len(w) >= 4 and w not in STOP:
            out.append(w[:5])
    return out


def load_index():
    lines = []  # (url, dom, toks_set, raw_text)
    for f in sorted(NOTES.glob("*.md")):
        body = f.read_text(encoding="utf-8").splitlines()
        url = re.match(r"#\s*(\S+)", body[0]).group(1)
        dom = re.sub(r"^www\.", "", url.split("/")[2])
        for ln in body:
            t = ln.strip()
            if not t.startswith("- "):
                continue
            txt = re.sub(r"^-\s*(\[[A-Z_А-ЯЁ ]+\]\s*)*", "", t)
            tt = toks(txt)
            if tt:
                lines.append((url, dom, set(tt), txt))
    df = defaultdict(int)
    for _, _, s, _ in lines:
        for w in s:
            df[w] += 1
    n = len(lines)
    idf = {w: math.log(1.0 + n / (1.0 + c)) for w, c in df.items()}
    return lines, idf


def score(q_tokens, q_set, entry_set, idf):
    if not q_set or not entry_set:
        return 0.0, 0.0
    inter = q_set & entry_set
    wsum = sum(idf.get(w, 0.0) for w in inter)
    containment = wsum / sum(idf.get(w, 0.0) for w in q_set)
    jacc = wsum / sum(idf.get(w, 0.0) for w in (q_set | entry_set))
    return containment, jacc


def main():
    lines, idf = load_index()
    print("index lines: %d" % len(lines), file=sys.stderr)
    doc_lines = read_all().splitlines()
    items = []
    for i, ln in enumerate(doc_lines, 1):
        t = ln.strip()
        if not (t.startswith("- ") or re.match(r"^\d+\.\s+\*\*", t) or t.startswith("|")):
            continue
        if re.match(r"^\d+\.\s+<https?://", t):
            continue
        body = re.sub(r"^[-\d.\s|]+\s*", "", t)
        if len(body) < 25:
            continue
        items.append((i, body))
    print("doc items to attribute: %d" % len(items), file=sys.stderr)

    report = []
    hist = defaultdict(int)
    for lineno, body in items:
        qt = toks(body)
        qs = set(qt)
        if len(qs) < 2:
            hist["too_few_tokens"] += 1
            continue
        bysrc = {}
        for url, dom, s, txt in lines:
            c, j = score(qt, qs, s, idf)
            sc = 0.7 * c + 0.3 * j
            key = url
            if key not in bysrc or bysrc[key][0] < sc:
                bysrc[key] = (sc, c, txt)
        top = sorted(bysrc.items(), key=lambda kv: -kv[1][0])[:3]
        best = top[0][1][0]
        second = top[1][1][0] if len(top) > 1 else 0.0
        bucket = "strong" if best >= 0.62 else ("medium" if best >= 0.42 else "weak")
        if bucket in ("medium", "weak") and best - second < 0.05:
            bucket += "-tie"
        hist[bucket] += 1
        report.append({
            "line": lineno, "text": body[:160], "best": round(best, 3),
            "second": round(second, 3), "bucket": bucket,
            "top": [(u, round(s[0], 3), s[2][:90]) for u, s in top],
        })
    with (BASE / "attr_report.json").open("w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print(json.dumps(dict(hist), ensure_ascii=False), file=sys.stderr)
    for r in report[:12]:
        print("%d [%s b=%.2f s=%.2f] %s\n   -> %s" % (
            r["line"], r["bucket"], r["best"], r["second"], r["text"][:90],
            r["top"][0][0]))


main()
