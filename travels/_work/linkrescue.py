# -*- coding: utf-8 -*-
"""Спасающий проход: строки, которые не получили URL в linkverify.

Подзаголовки (**Тема:**) и служебные строки (перечни «чего в источниках нет») не трогаем;
для остальных переспрашиваем модель, а если и тогда пусто — берём лексический топ-1 при
высоком сходстве (score >= 0.70) и помечаем method=lexical.
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import Cache, call_llm  # noqa: E402
from linklib import Index, link_numbers, toks  # noqa: E402

BASE = Path(__file__).resolve().parent
WORK = BASE / "linkify_work.json"
DEC = BASE / "linkify_decisions.json"
MODEL = "auto"
BATCH = 4
LEX_MIN = 0.70

SUBHEAD_RE = re.compile(r"^\*\*[^*]+\*\*:?\s*$|^\*\*[^*]+[:.]?\*\*:?\s*$")
SERVICE_RE = re.compile(r"в обработанных|не найдено|не разбор|легенда|помечания|служеб|не входили|не анализировал", re.I)

PREAMBLE = """Задача — атрибуция источника. Для каждой строки справочника перечислены кандидаты:
фрагменты текстов статей, откуда строка могла вырасти.
1) Выбери кандидатов, чей фрагмент реально содержит этот факт (тот же объект/топоним, цифра, год, суть).
2) Строка может склеивать несколько фактов из разных статей — тогда назови всех подходящих, до трёх.
3) Если ни один фрагмент факт не содержит — верни 0. Не додумывай по внешним знаниям.
4) Номера кандидатов — только те, что перечислены внутри записи (1, 2, 3…).
5) Формат: строго одна строка на запись: `<id>: <номера через запятую>` или `<id>: 0`. Без пояснений.
"""


def prompt_for(chunk):
    parts = [PREAMBLE]
    for r in chunk:
        parts.append("\n[запись %d] %s" % (r["id"], r["text"]))
        for n, c in enumerate(r["cands"], 1):
            parts.append("   %d) %s\n      фрагмент: %s" % (n, c["url"], c["snip"]))
    parts.append("\nОтвет:")
    return "\n".join(parts)


def parse(text, r):
    by_idx = {i: c["url"] for i, c in enumerate(r["cands"], 1)}
    urls = []
    for ln in text.splitlines():
        m = re.match(r"^\s*(\d+)\s*[:\-\)]\s*(.+)$", ln.strip())
        if not m or int(m.group(1)) != r["id"]:
            continue
        for n in (int(x) for x in re.findall(r"\d+", m.group(2))):
            u = by_idx.get(n)
            if u and u not in urls:
                urls.append(u)
    return urls[:3]


def main():
    work = json.load(open(WORK, encoding="utf-8"))
    dec = json.load(open(DEC, encoding="utf-8"))
    nums = link_numbers()
    idx = Index()
    idx.finish_idf()

    todo = []
    for r in work:
        if dec.get(str(r["id"]), {}).get("urls"):
            continue
        t = r["text"]
        if SUBHEAD_RE.match(t) or len(t.rstrip()) < 45 and t.rstrip().endswith(":") or SERVICE_RE.search(t):
            dec[str(r["id"])] = {"urls": [], "file": r["file"], "line": r["line"],
                                 "score": r["score"], "method": "meta"}
            continue
        q = set(toks(t))
        cand = idx.best_for(q, urls=set(nums))[:6]
        todo.append({"id": r["id"], "file": r["file"], "line": r["line"], "text": t, "score": r["score"],
                     "cands": [{"url": u, "num": nums.get(u, 0), "kind": k, "snip": s[:230]}
                               for u, sc, k, s in cand],
                     "lex_top": cand[0][0] if cand and cand[0][1] >= LEX_MIN else None})
    DEC.write_text(json.dumps(dec, ensure_ascii=False, indent=1), encoding="utf-8")
    print("к переспросу: %d, мета-строк помечено: %d" % (len(todo), len(work) - len(todo)),
          file=sys.stderr)

    cache = Cache()
    chunks = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]

    def run(ch):
        key = "linkrescue:" + "|".join(str(r["id"]) for r in ch)
        raw = cache.get(key)
        if raw is None:
            raw = call_llm(prompt_for(ch), MODEL, max_tokens=800, temp=0.0)
            cache.put(key, raw)
        for r in ch:
            urls = [u for u in parse(raw, r) if u in nums]
            method = "llm-rescue"
            if not urls and r["lex_top"]:
                urls, method = [r["lex_top"]], "lexical"
            entry = {"urls": urls[:3], "file": r["file"], "line": r["line"],
                     "score": r["score"], "method": method if urls else "unresolved"}
            old = dec.get(str(r["id"]), {})
            old.update(entry)
            dec[str(r["id"])] = entry
        return len(ch)

    with ThreadPoolExecutor(max_workers=3) as ex:
        done = 0
        for n in ex.map(run, chunks):
            done += n
            print("  %d/%d" % (done, len(todo)), file=sys.stderr, flush=True)
        DEC.write_text(json.dumps(dec, ensure_ascii=False, indent=1), encoding="utf-8")

    linked = sum(1 for v in dec.values() if v["urls"])
    print("итог: решений %d, со ссылкой %d, без %d" % (len(dec), linked, len(dec) - linked),
          file=sys.stderr)


main()
