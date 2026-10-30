# -*- coding: utf-8 -*-
"""Проверяет каждую проставленную ссылку: содержит ли этот источник то, о чём сказано в пункте.

Отличительные токены строки — слова длиннее 5 букв (нормализация ё→е) и все числовые цепочки.
Ссылка подозрительна, если ни один такой токен не встречается ни в полном тексте источника (raw/*.json),
ни в его выжимке (notes/*.md). Для склеенных из нескольких источников строк проверка по каждой URL
отдельная, поэтому ложные срабатывания возможны и читаются руками.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docparts import read_all  # noqa: E402
from linklib import link_numbers  # noqa: E402

BASE = Path(__file__).resolve().parent
MARK_RE = re.compile(r"\[→(\d+)\]\((https?://[^)]+)\)")
WORD_RE = re.compile(r"[а-яёa-z]{6,}")
NUM_RE = re.compile(r"\d[\d\s]{0,9}\d|\d")


def norm(s):
    return s.lower().replace("ё", "е")


def slug(url):
    tail = re.sub(r"^https?://", "", url).split("/")
    return (tail[-1] or (tail[-2] if len(tail) > 1 else "")).strip("/").lower().replace("ё", "е")[:40]


def load_corpus():
    """url → нормализованный текст (raw + notes вместе)."""
    corp = {}
    for p in (BASE / "raw").glob("*.json"):
        d = json.load(open(p, encoding="utf-8"))
        if d.get("url"):
            corp[d["url"]] = [norm(d.get("text") or "")]
    for p in (BASE / "notes").glob("*.md"):
        t = open(p, encoding="utf-8").read().splitlines()
        url = t[0].lstrip("# ").strip() if t else None
        if url:
            corp.setdefault(url, []).append(norm("\n".join(t[1:])))
    joined = {u: " \n ".join(v) for u, v in corp.items()}
    # зеркала (t-j.ru вместо journal.tinkoff.ru) и хвосты URL: сопоставляем по последнему сегменту пути
    by_slug = {}
    for u, txt in joined.items():
        by_slug.setdefault(slug(u), txt)
    return joined, by_slug


def text_for(url, corp, by_slug):
    return corp.get(url) or by_slug.get(slug(url)) or ""


def main():
    nums = {v: k for k, v in link_numbers().items()}
    corp, by_slug = load_corpus()
    docs = [read_all().splitlines()]
    rows = []
    for i, ln in enumerate(docs[0], 1):
        if not re.match(r"^\s*(-|\d+\.)\s+", ln):
            continue
        marks = MARK_RE.findall(ln)
        body = MARK_RE.sub("", ln)
        body = re.sub(r"`\[[^`]*\]`", " ", body)
        text = norm(re.sub(r"\*+", "", body))
        toks = set(WORD_RE.findall(text))
        for num in NUM_RE.findall(text):
            toks.update(num.split())
        if not toks or not marks:
            continue
        rows.append((i, ln.strip(), toks, marks))

    bad = []
    for i, ln, toks, marks in rows:
        miss = []
        for n, url in marks:
            c = text_for(url, corp, by_slug)
            hit = [t for t in toks if t in c]
            cov = len(hit) / float(len(toks))
            if cov < 0.18 or not hit:
                miss.append((n, url, round(cov, 2), sorted(hit, key=len)[-3:]))
        if miss:
            bad.append((i, ln, miss))

    print("строк со ссылками: %d, с подозрительной URL: %d" % (len(rows), len(bad)))
    filt = sys.argv[1] if len(sys.argv) > 1 else None
    shown = 0
    for i, ln, miss in bad:
        if filt and filt not in ln:
            continue
        shown += 1
        if shown > 60:
            break
        print("\nL%d| %s" % (i, ln[:190]))
        for n, url, cov, hit in miss:
            print("      → %s (%s) совпадений %.2f; есть слова: %s" % (
                n, url.replace("https://", "")[:46], cov, ", ".join(hit)[:80]))


main()
