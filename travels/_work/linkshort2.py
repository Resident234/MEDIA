# -*- coding: utf-8 -*-
"""Точечный третий проход: строки, которые провалились между первыми двумя.

Это пункты ровно 24 знака (первый брал >=25, второй — 8..23), абзацы прозы
(не начинаются с «- ») и строки, где осталась снятая укрупнённая метка.
Список targets ниже составлен по отчёту linkcover.py.
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
MODEL, BATCH = "auto", 5
LEX_MIN, PRIOR_MIN = 0.50, 2

TARGETS = [
    ("places__Бадахшан_Хорог_Рощан_Шугнан_Ишкошим_Вахан_Зоркуль_Мургаб_Памирский_тракт.md", 16),
    ("places__Бадахшан_Хорог_Рощан_Шугнан_Ишкошим_Вахан_Зоркуль_Мургаб_Памирский_тракт.md", 59),
    ("places__Бадахшан_Хорог_Рощан_Шугнан_Ишкошим_Вахан_Зоркуль_Мургаб_Памирский_тракт.md", 200),
    ("places__нурек.md", 17),
    ("places__Хатлон_Бохтар_Курган-Тюбе_Куляб_Шаартуз_Вахда.md", 18),
    ("places__Худжанд.md", 19),
    ("транспорт_связь.md", 82),
    ("транспорт_связь.md", 107),
    ("70_pokupki.md", 50),
    ("30_dengi.md", 51),
    ("90_med.md", 42),
    ("40_transport.md", 79),
    ("95_zametki.md", 83),
]

PREAMBLE = """Нужно привязать пункт справочника к конкретному источнику из списка.
1) Кандидаты — фрагменты текстов статей. Бери тот, где этот объект, цифра или формулировка действительно есть.
2) «блок» — источник, из которого взяты соседние строки этого же подраздела; бери его, если фрагмент подходит или объект логично там же.
3) Ни один фрагмент не содержит того, о чём сказано в пункте, — верни 0. Выдумывать источник нельзя.
4) Формат ответа: `<id>: <номер кандидата>` или `<id>: 0`, по строке на запись, без пояснений.
"""


def neighbours(lines, n, k=10):
    """URL уже атрибутированных строк вокруг целевой — по две в каждую сторону."""
    out, left, right = [], [], []
    for i in range(n - 1, max(0, n - 1 - 25), -1):
        m = re.search(r"\[→(\d+)\]\(http", lines[i - 1]) if i <= len(lines) else None
        if m:
            left.append(int(m.group(1)))
        if len(left) >= k // 2:
            break
    for i in range(n + 1, min(len(lines), n + 25) + 1):
        m = re.search(r"\[→(\d+)\]\(http", lines[i - 1])
        if m:
            right.append(int(m.group(1)))
        if len(right) >= k // 2:
            break
    return left + right


def main():
    nums = link_numbers()
    urls_by_num = {v: k for k, v in nums.items()}
    idx = Index()
    idx.finish_idf()
    cache_files = {}
    for name in {f for f, _ in TARGETS}:
        p = (BUILD / name) if (BUILD / name).exists() else (SECT / name)
        cache_files[name] = p.read_text(encoding="utf-8").splitlines()

    todo = []
    for rel, n in TARGETS:
        lines = cache_files[rel]
        raw = lines[n - 1].strip()
        text = re.sub(r"^\s*-\s+", "", raw)
        text = re.sub(r"\s*\[→\d+\]\(http[^)]*\)", "", text)
        text = re.sub(r"`\[(?:Т—Ж 2026|полевой опыт|aviasales|onetwotrip|tengritravel)\]`", "", text).strip()
        head = ""
        for j in range(n - 2, max(0, n - 12), -1):
            h = lines[j].strip()
            if h.startswith("### "):
                head = h[4:]
                break
        q = set(toks(text))
        lex = idx.best_for(q, urls=set(nums)) if q else []
        prior = Counter(urls_by_num.get(v) for v in neighbours(lines, n))
        block = [u for u, c in prior.most_common(3) if u and c >= PRIOR_MIN]
        cands = [(u, snip, "лекс.") for u, _sc, _k, snip in lex[:4]]
        for u in block:
            if u not in [c[0] for c in cands]:
                snip = next((s for uu, _sc, _k, s in idx.best_for(q, urls={u}) or []), "")
                cands.append((u, snip or "источник соседних строк этого блока", "блок"))
        todo.append({"id": len(todo), "file": rel, "line": n, "text": text, "head": head,
                     "block": block,
                     "cands": [{"url": u, "snip": s[:220], "why": w} for u, s, w in cands[:5]],
                     "lex_top": lex[0][0] if lex and lex[0][1] >= LEX_MIN else None})
    json.dump(todo, open(BASE / "link_extra_work.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("строк к точечному проходу: %d" % len(todo), file=sys.stderr)
    for r in todo:
        print("  [%s:%d] %s | cands=%d block=%d" % (
            r["file"][:18], r["line"], r["text"][:60], len(r["cands"]), len(r["block"])),
            file=sys.stderr)
    if "--dry" in sys.argv:
        return

    cache = Cache()
    chunks = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]

    def prompt(ch):
        parts = [PREAMBLE]
        for r in ch:
            parts.append("\n[запись %d] раздел «%s», пункт: %s" % (r["id"], r["head"], r["text"]))
            for i, c in enumerate(r["cands"], 1):
                parts.append("   %d) [%s] %s\n      фрагмент: %s" % (i, c["why"], c["url"], c["snip"]))
            if not r["cands"]:
                parts.append("   (кандидатов нет)")
        return "\n".join(parts) + "\n\nОтвет:"

    def run(ch):
        key = "linkextra:" + "|".join("%s:%s" % (r["file"], r["line"]) for r in ch)
        raw = cache.get(key)
        if raw is None:
            raw = call_llm(prompt(ch), MODEL, max_tokens=600, temp=0.0)
            cache.put(key, raw)
        res = {}
        for r in ch:
            pick = None
            for ln in raw.splitlines():
                m = re.match(r"^\s*(\d+)\s*[:\-\)]\s*(\d+)", ln.strip())
                if m and int(m.group(1)) == r["id"]:
                    k = int(m.group(2))
                    if 1 <= k <= len(r["cands"]):
                        pick = r["cands"][k - 1]["url"]
                    break
            if pick:
                res[r["id"]] = [pick, "llm-extra"]
            elif r["cands"] and r["cands"][0]["why"] == "лекс.":
                res[r["id"]] = [r["cands"][0]["url"], "lexical"]
            elif r["block"]:
                res[r["id"]] = [r["block"][0], "block-prior"]
            else:
                res[r["id"]] = [None, "unresolved"]
        return res

    with ThreadPoolExecutor(max_workers=3) as ex:
        allres = {}
        for r in ex.map(run, chunks):
            allres.update(r)
    json.dump(allres, open(BASE / "link_extra_result.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("получено: %d из %d" % (sum(1 for v in allres.values() if v[0]), len(allres)),
          file=sys.stderr)
    for rid, (u, how) in sorted(allres.items(), key=lambda x: int(x[0])):
        r = todo[rid]
        print("  %-12s %s:%d %s\n        -> %s" % (
            how, r["file"][:22], r["line"], r["text"][:70], u or "-"), file=sys.stderr)


main()
