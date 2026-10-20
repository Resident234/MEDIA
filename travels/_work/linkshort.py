# -*- coding: utf-8 -*-
"""Доставляет ссылки коротким пунктам (8–24 зн.), которые проходили мимо первого прохода.

Для такого пункта фактического текста мало, зато надёжен контекст: заголовок подраздела и
соседние строки, уже атрибутированные. Кандидаты = лексический топ по корпусу + частотные
источники окрестных строк; решение — моделью, при отказе — источник соседей (method=block-prior).
"""
import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import Cache, call_llm  # noqa: E402
from linklib import Index, link_numbers, toks  # noqa: E402

BASE = Path(__file__).resolve().parent
BUILD = BASE / "build"
SECT = BASE / "sections"
DEC = BASE / "linkify_decisions.json"
MODEL, BATCH = "auto", 6
LEX_MIN, PRIOR_MIN = 0.55, 3

SUB_RE = re.compile(r"^(\*\*[^*]+[:.]?\*\*|\*\*[^*]+\*\*:?)\s*$")
SVC_RE = re.compile(r"в источниках не найдено|не обработано|Как проставлены|Прежние укрупн|дословно|Вывод \(наш|Практический вывод|Ориентиры по")

PREAMBLE = """Краткий пункт справочника (название объекта + минимальная характеристика) нужно привязать к источнику.
Контекст: раздел, подзаголовок и соседние строки уже атрибутированы — их источники указаны вprior'е.
1) Кандидаты — фрагменты текстов статей. Выбирай тот, где этот объект (то же название, та же цифра) действительно упоминается.
2) Если подходит источник соседей и в его фрагменте объект есть — бери его.
3) Ни один фрагмент не содержит объект — верни 0.
4) Формат: `<id>: <номер кандидата>` или `<id>: 0`, по одной строке на запись, без пояснений.
"""


def bullets(path):
    """(файл, номер строки, текст, отступ) всех пунктов."""
    out = []
    for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = re.match(r"^(\s*)-\s+(.*)$", ln)
        if m:
            out.append((i, m.group(1), m.group(2)))
    return out


def main():
    nums = link_numbers()
    urls_by_num = {v: k for k, v in nums.items()}
    dec = json.loads(DEC.read_text(encoding="utf-8"))
    idx = Index()
    idx.finish_idf()

    todo = []
    for f in sorted((BUILD).glob("*.md")) + sorted(SECT.glob("*.md")):
        if f.name == "links.md":
            continue
        rel, bs = f.name, bullets(f)
        # маркер [→N] уже вставлен в те строки файла, что покрыты первым проходом
        linked_at = {}
        for r_line, ind, body in bs:
            m = re.search(r"\[→(\d+)\]\(http", body)
            if m:
                linked_at[r_line] = urls_by_num.get(int(m.group(1)))
        raw_lines = f.read_text(encoding="utf-8").splitlines()
        head, sub, near = "", "", []
        for r_line, ind, body in bs:
            text = re.sub(r"\s*\[→\d+\]\(http[^)]*\)", "", body).strip()
            for j in range(r_line - 2, max(0, r_line - 8), -1):
                h = raw_lines[j].strip()
                if h.startswith("### ") and not head:
                    head = h[4:]
                    break
            if SUB_RE.match(text):
                sub = re.sub(r"\*+", "", text).rstrip(": ")
                near = []
                continue
            if len(text) >= 24 or len(text) < 8 or SVC_RE.search(text) or text.rstrip().endswith(":"):
                if len(text) >= 24:
                    near.append((r_line, linked_at.get(r_line)))
                continue
            prior = Counter(u for _, u in near[-8:] if u)
            block = [u for u, c in prior.most_common(2) if c >= PRIOR_MIN]
            q = set(toks(text))
            lex = idx.best_for(q, urls=set(nums)) if q else []
            lex_top = lex[0] if lex and lex[0][1] >= LEX_MIN else None
            cand_urls = []
            for u, sc, k, s in lex[:3]:
                cand_urls.append((u, s, "лекс."))
            for u in block:
                if u not in [c[0] for c in cand_urls]:
                    snip = next((s for uu, sc, k, s in idx.best_for(q, urls={u}) or []), "")
                    cand_urls.append((u, snip or "источник соседних строк этого блока", "блок"))
            near.append((r_line, linked_at.get(r_line)))
            todo.append({"id": len(todo), "file": rel, "line": r_line, "text": text,
                         "head": head, "sub": sub, "block": block,
                         "cands": [{"url": u, "snip": s[:200], "why": w} for u, s, w in cand_urls[:4]],
                         "lex_top": lex_top[0] if lex_top else None})
    print("коротких строк к достройке: %d" % len(todo), file=sys.stderr)
    json.dump(todo, open(BASE / "link_short_work.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    if "--dry" in sys.argv:
        for r in todo[:12]:
            print("  [%s:%d] %s | head=%s sub=%s block=%s cands=%d" % (
                r["file"][:22], r["line"], r["text"][:48], r["head"][:22], r["sub"][:22],
                [b.split("/")[2][:18] for b in r["block"]], len(r["cands"])), file=sys.stderr)
        return

    cache = Cache()
    chunks = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]

    def prompt(ch):
        parts = [PREAMBLE]
        for r in ch:
            parts.append("\n[запись %d] раздел «%s», подзаголовок «%s», пункт: %s" % (
                r["id"], r["head"], r["sub"], r["text"]))
            for n, c in enumerate(r["cands"], 1):
                parts.append("   %d) [%s] %s\n      фрагмент: %s" % (n, c["why"], c["url"], c["snip"]))
            if not r["cands"]:
                parts.append("   (кандидатов нет)")
        return "\n".join(parts) + "\n\nОтвет:"

    def run(ch):
        key = "linkshort:" + "|".join("%s:%s" % (r["file"], r["line"]) for r in ch)
        raw = cache.get(key)
        if raw is None:
            raw = call_llm(prompt(ch), MODEL, max_tokens=700, temp=0.0)
            cache.put(key, raw)
        res = {}
        for r in ch:
            pick = None
            for ln in raw.splitlines():
                m = re.match(r"^\s*(\d+)\s*[:\-\)]\s*(\d+)", ln.strip())
                if m and int(m.group(1)) == r["id"]:
                    n = int(m.group(2))
                    if 1 <= n <= len(r["cands"]):
                        pick = r["cands"][n - 1]["url"]
                    break
            if pick:
                res[r["id"]] = (pick, "llm-short")
            elif r["block"]:
                res[r["id"]] = (r["block"][0], "block-prior")
            elif r["lex_top"]:
                res[r["id"]] = (r["lex_top"], "lexical")
            else:
                res[r["id"]] = (None, "unresolved")
        return res

    with ThreadPoolExecutor(max_workers=3) as ex:
        allres = {}
        for r in ex.map(run, chunks):
            allres.update(r)
    got = sum(1 for v in allres.values() if v[0])
    print("получено ссылок: %d из %d" % (got, len(allres)), file=sys.stderr)
    json.dump(allres, open(BASE / "link_short_result.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    for rid, (u, how) in sorted(allres.items()):
        if how != "llm-short":
            r = next(x for x in todo if x["id"] == rid)
            print("   %-10s %s:%d %s -> %s" % (how, r["file"][:20], r["line"], r["text"][:40],
                                               u.split("/")[2] if u else "-"), file=sys.stderr)


main()
