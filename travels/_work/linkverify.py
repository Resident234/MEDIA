# -*- coding: utf-8 -*-
"""LLM-верификация атрибуции: для каждой строки выбираем URL-источник из кандидатов.

Резюме: candidates считаются лексически (linklib), решение по каждому — моделью `auto`
через локальный прокси. Результаты кэшируются (llm_cache.jsonl) и пишутся в
linkify_decisions.json: (файл, номер строки) -> [URL, ...].
"""
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import Cache, call_llm  # noqa: E402
from linklib import Index, link_numbers, toks  # noqa: E402

BASE = Path(__file__).resolve().parent
BUILD = BASE / "build"
SECT = BASE / "sections"
OUT = BASE / "linkify_decisions.json"
WORK = BASE / "linkify_work.json"
SKIP = {"links.md"}
TAG_RE = re.compile(r"`\[([^\]]+)\]`")
N_CAND = 6
BATCH = 8
MODEL = "auto"

PREAMBLE = """Задача — атрибуция. Даны строки справочника о Таджикистане и кандидаты-источники:
для каждой строки подобраны фрагменты текстов статей, из которых эта строка могла вырасти.

Правила:
1) Выбери кандидатов (максимум два), чьи фрагменты реально содержат тот же факт: топоним/объект,
   цифра, год, название, суть утверждения. Дубликаты одного и того же источника не нужны.
2) Если ни один фрагмент факт не содержит — верни 0. Не угадывай по внешним знаниям.
3) Строки-служебные (легенда помечания, перечисление того, чего в источниках нет, выводы редактора,
   оглавления) — всегда 0.
4) Номера кандидатов — только те, что перечислены внутри записи (1, 2, 3…). Отвечай этими номерами,
   а не номерами статей и не URL.
5) Формат ответа строго по одной строке на каждую запись: `<id>: <номера через запятую>` или `<id>: 0`.
   Никакого другого текста, никаких пояснений.
"""


def target_lines():
    files = sorted(BUILD.glob("*.md")) + sorted(SECT.glob("*.md"))
    for f in files:
        if f.name in SKIP:
            continue
        for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            t = ln.strip()
            if not t.startswith("- ") or len(t[2:]) < 25:
                continue
            yield f.name, i, t[2:], TAG_RE.findall(t)


def build_work():
    idx = Index()
    idx.finish_idf()
    nums = link_numbers()
    rows = []
    for fname, lineno, body, tags in target_lines():
        q = set(toks(body))
        if len(q) < 2:
            rows.append({"id": len(rows), "file": fname, "line": lineno, "text": body,
                         "tags": tags, "cands": [], "score": 0.0})
            continue
        cand = idx.best_for(q)[:N_CAND]
        rows.append({
            "id": len(rows), "file": fname, "line": lineno, "text": body, "tags": tags,
            "score": round(cand[0][1], 3) if cand else 0.0,
            "cands": [{"url": u, "num": nums.get(u, 0), "kind": k, "snip": s[:230]}
                      for u, sc, k, s in cand],
        })
    WORK.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return rows, nums


def prompt_for(chunk):
    parts = [PREAMBLE]
    for r in chunk:
        parts.append("\n[запись %d] %s" % (r["id"], r["text"]))
        for n, c in enumerate(r["cands"], 1):
            parts.append("   %d) %s\n      фрагмент: %s" % (n, c["url"], c["snip"]))
        if not r["cands"]:
            parts.append("   (кандидатов нет)")
    parts.append("\nОтвет:")
    return "\n".join(parts)


def parse(text, chunk):
    out = {}
    for r in chunk:
        by_idx = {i: c["url"] for i, c in enumerate(r["cands"], 1)}
        by_num = {c["num"]: c["url"] for c in r["cands"] if c["num"]}
        out[r["id"]] = []
        for ln in text.splitlines():
            ln = ln.strip().lstrip("#*")
            m = re.match(r"^(\d+)\s*[:\-\)]\s*(.+)$", ln)
            if not m or int(m.group(1)) != r["id"]:
                continue
            for n in (int(x) for x in re.findall(r"\d+", m.group(2))):
                # модель иногда отвечает глобальным номером из списка ссылок вместо индекса
                url = by_idx.get(n) or by_num.get(n)
                if url and url not in out[r["id"]]:
                    out[r["id"]].append(url)
        out[r["id"]] = out[r["id"]][:2]
    return out


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    rows = json.loads(WORK.read_text(encoding="utf-8")) \
        if WORK.exists() and only == "reuse" else build_work()[0]
    print("rows=%d" % len(rows), file=sys.stderr)
    cache = Cache()
    lock = threading.Lock()
    decisions = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    by_id = {r["id"]: r for r in rows}

    # сортируем: сначала слабые и спорные — их решение модели важнее всего
    order = sorted(rows, key=lambda r: r["score"])
    chunks = [order[i:i + BATCH] for i in range(0, len(order), BATCH)]

    def run(ch):
        key = "linkverify:" + "|".join("%s:%s" % (r["file"], r["line"]) for r in ch)
        raw = cache.get(key)
        if raw is None:
            raw = call_llm(prompt_for(ch), MODEL, max_tokens=1200, temp=0.0)
            with lock:
                cache.put(key, raw)
        res = parse(raw, ch)
        with lock:
            for rid, urls in res.items():
                row = by_id[rid]
                decisions[str(rid)] = {"urls": urls, "file": row["file"], "line": row["line"],
                                       "score": row["score"]}
            OUT.write_text(json.dumps(decisions, ensure_ascii=False, indent=1), encoding="utf-8")
        return len(ch)

    with ThreadPoolExecutor(max_workers=4) as ex:
        done = 0
        for n in ex.map(run, chunks):
            done += n
            print("  %d/%d" % (done, len(rows)), file=sys.stderr, flush=True)
    linked = sum(1 for v in decisions.values() if v["urls"])
    print("decisions=%d linked=%d unresolved=%d" % (len(decisions), linked, len(decisions) - linked),
          file=sys.stderr)


if __name__ == "__main__":
    main()
