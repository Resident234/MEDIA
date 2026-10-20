from __future__ import annotations

import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import Cache, call_llm  # noqa: E402

CACHE = Cache()

BASE = Path(__file__).resolve().parent
GROUPS = BASE / "groups"
SECTIONS = BASE / "sections"
SECTIONS.mkdir(parents=True, exist_ok=True)

RULES = """ЖЁСТКИЕ ПРАВИЛА:
1) Пиши ТОЛЬКО по переданному списку фактов. Не додумывай, не добавляй внешних знаний, не «уточняй» цены и даты.
2) Сохраняй все конкретные названия (топонимы, улицы, здания, авторы проектов, годы, высоты, расстояния, цены в сомони/долларах) — они главная ценность.
3) Убирай повторы и смысловые дубликаты: одно и то же утверждение — одна строка.
4) Строки вида «получение регистрации в Душанбе», «перелёт Москва — Душанбе», «упомянуто в оглавлении» — мусор из оглавлений, их выбрасывай.
5) Мнения автора помечай коротко: (мнение автора).
6) Формат вывода — markdown-список (- ) с жирными подзаголовками (**...**) по подтемам или объектам. Никакого вступительного текста.
7) Пиши по-русски. Не сокращай список произвольно: должно остаться не меньше 70% исходных пунктов по смыслу."""


def condense_prompt(facts: str, kind: str) -> str:
    return f"""Ты редакторtravel-справочника по Таджикистану. Ниже — размеченные факты, собранные из статей.
Приведи их к плотному, читаемому конспекту. {RULES}

ЗАДАЧА: {kind}

ФАКТЫ:
{facts}
"""


def pack_lines(text: str, size: int = 8500) -> list[str]:
    lines = [l for l in text.splitlines() if l.strip()]
    chunks, cur, n = [], [], 0
    for l in lines:
        if n + len(l) + 1 > size and cur:
            chunks.append("\n".join(cur))
            cur, n = [], 0
        cur.append(l)
        n += len(l) + 1
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def run_one(path: Path, kind: str, out: Path, model: str, merge_model: str) -> str:
    text = path.read_text(encoding="utf-8")
    chunks = pack_lines(text, 8500)
    parts = []
    for i, ch in enumerate(chunks, 1):
        key = f"cond:{path.name}:{i}:{kind}"
        cached = CACHE.get(key)
        if cached is None:
            t0 = time.time()
            cached = call_llm(condense_prompt(ch, kind), model, max_tokens=8000, temp=0.2)
            CACHE.put(key, cached)
            print(f"  {path.name} chunk {i}/{len(chunks)} (+{time.time()-t0:.0f}s)")
        parts.append(cached)
    if len(parts) == 1:
        res = parts[0]
    else:
        key = f"merge:{path.name}:{kind}"
        res = CACHE.get(key)
        if res is None:
            body = "\n\n----\n\n".join(parts)
            res = call_llm(
                f"Соедини несколько конспектов одного и того же материала в один без повторов. {RULES}\n\n{body}",
                merge_model, max_tokens=8000, temp=0.2,
            )
            CACHE.put(key, res)
            print(f"  {path.name} merge ({len(parts)} parts)")
    out.write_text(res, encoding="utf-8")
    return f"OK {out.name}: {len(text)} -> {len(res)} ch"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="places__*.txt")
    ap.add_argument("--kind", default="Это список достопримечательностей, зданий и мест по одному региону Таджикистана. Сгруппируй по городам/кластерам и типу объектов (архитектура, музеи, базары, природа, храмы), внутри — кратко и фактологично.")
    ap.add_argument("--model", default="auto")
    ap.add_argument("--merge-model", default="auto")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()

    files = sorted(GROUPS.glob(args.glob))
    tasks = [(f, SECTIONS / (f.stem + ".md")) for f in files]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(run_one, f, args.kind, out, args.model, args.merge_model) for f, out in tasks]
        for fu in futs:
            print(fu.result())


if __name__ == "__main__":
    main()
