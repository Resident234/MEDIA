from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
RAW = BASE / "raw"
NOTES = BASE / "notes"
NOTES.mkdir(parents=True, exist_ok=True)
CACHE = BASE / "llm_cache.jsonl"

API_URL = os.environ.get("LLM_URL", "http://127.0.0.1:31415/v1/chat/completions")
API_KEY = os.environ.get("LLM_KEY", "freellmapi-c50ce86439ddb286b2815f9973fe2c0788ac1f66d6b966e7")

TOPICS = ("ВИЗА_РЕГИСТРАЦИЯ", "ЖИЛЬЕ", "БАНКИ_ДЕНЬГИ", "ТРАНСПОРТ_СВЯЗЬ",
          "МЕСТА_АРХИТЕКТУРА", "ЕДА_АЛКОГОЛЬ", "ПОКУПКИ_РЫНКИ_ТЦ",
          "МЕДИЦИНА_СТРАХОВКА", "ПРОЧЕЕ")

EXTRACT_PROMPT = """Ты внимательно анализируешь travel-заметку о Таджикистане (путевые дневники, обзоры городов, статьи о переезде).
Извлеки ТОЛЬКО то, что явно написано в тексте. Не додумывай, не дополняй своими знаниями, не переформулируй числа.

Формат ответа: только строки списка вида
- [ТЕМА] факт

ТЕМЫ: ВИЗА_РЕГИСТРАЦИЯ, ЖИЛЬЕ, БАНКИ_ДЕНЬГИ, ТРАНСПОРТ_СВЯЗЬ, МЕСТА_АРХИТЕКТУРА, ЕДА_АЛКОГОЛЬ, ПОКУПКИ_РЫНКИ_ТЦ, МЕДИЦИНА_СТРАХОВКА, ПРОЧЕЕ

Правила:
- Сохраняй все конкретные детали: цены, валюты и суммы, даты, годы постройки, расстояния, время в пути, названия улиц, зданий, отелей, чайхан, ресторанов, рынков, ТЦ, банков, перевозчиков, операторов связи, городов и ущелий.
- МЕСТА_АРХИТЕКТУРА: каждый памятник/здание отдельной строкой с годом, автором, стилем, особенностями, если указаны.
- ТРАНСПОРТ_СВЯЗЬ: маршруты, виды транспорта, где купить билет, стоимость, продолжительность, дороги и перевалы, границы и КПП, SIM-карты, интернет.
- ЕДА_АЛКОГОЛЬ: заведения с названиями, кухня, цены, атмосфера; отдельной строкой — всё про алкоголь, спиртное, запрет/разрешение, где продают.
- ЖИЛЬЕ: отели, хостелы, гостевые дома, квартиры, цены, где искать, регистрации у хозяев.
- БАНКИ_ДЕНЬГИ: банки, карты, банкоматы, обмен валюты, переводы, наличные, курсы, рынки и цены на товары, если это покупки.
- ВИЗА_РЕГИСТРАЦИЯ: виза, миграционная карта, сроки пребывания, прописка/регистрация, штрафы, разрешения на ГБАО/Памир, документы на границе.
- МЕДИЦИНА_СТРАХОВКА: больницы, аптеки, врачи, страховка, вакцинация, вода/еда с точки зрения здоровья, горная болезнь, высота.
- Субъективное помечай «(мнение автора)».
- Если по теме ничего нет — не пиши пустых строк. Дублируй не нужно.
- Объём: столько строк, сколько реальных фактов в тексте, максимально полно.

ТЕКСТ:
"""

MERGE_PROMPT = """Ниже — выжимки фактов по кускам одной статьи о Таджикистане (та же статья, нарезанная по абзацам).
Собери их в один непротиворечивый список без дублей: склеивай повторы, сохраняй все числа, названия и пометки «(мнение автора)».
Формат: только строки вида - [ТЕМА] факт. Темы те же, что во входах. Ничего не добавляй от себя.

ВЫЖИМКИ:
"""


def call_llm(prompt: str, model: str, max_tokens: int = 8000, temp: float = 0.1, attempts: int = 8) -> str:
    last = ""
    for i in range(attempts):
        try:
            r = requests.post(
                API_URL,
                headers={"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"},
                json={"model": model, "temperature": temp, "max_tokens": max_tokens,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=900,
            )
            j = r.json()
            if "choices" in j:
                out = (j["choices"][0]["message"]["content"] or "").strip()
                if out:
                    return out
                last = "empty"
            else:
                last = json.dumps(j.get("error", {}), ensure_ascii=False)[:200]
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
        sleep = min(240, 12 * (2 ** i)) * (0.6 + random.random())
        print(f"    retry {i+1} in {sleep:.0f}s ({last[:80]})", flush=True)
        time.sleep(sleep)
    return f"__LLM_FAIL__ {last}"


def cache_key(tag: str) -> str:
    return hashlib.sha1(tag.encode("utf-8")).hexdigest()


def load_cache() -> dict:
    data = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            data[rec["k"]] = rec["v"]
    return data


class Cache:
    def __init__(self):
        self.d = load_cache()
        self.path = CACHE
        self.lock = threading.Lock()

    def get(self, k):
        return self.d.get(k)

    def put(self, k, v):
        with self.lock:
            self.d[k] = v
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"k": k, "v": v}, ensure_ascii=False) + "\n")


def split_chunks(text: str, size: int = 8000) -> list[str]:
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        while len(p) > size:
            cut = p.rfind(". ", 0, size)
            cut = cut + 1 if cut > size // 2 else size
            head, p = p[:cut], p[cut:]
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(head)
        if len(cur) + len(p) + 2 > size and cur:
            chunks.append(cur)
            cur = ""
        cur += (p + "\n\n")
    if cur.strip():
        chunks.append(cur)
    return chunks


def records() -> list[dict]:
    out = []
    for f in sorted(RAW.glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        if len(rec.get("text", "")) >= 300:
            rec["file"] = f.name
            out.append(rec)
    return out


def process(rec: dict, cache: Cache, model: str, only_new: bool) -> str:
    url, text = rec["url"], rec["text"]
    chunks = split_chunks(text)
    outs = []
    changed = False
    for i, ch in enumerate(chunks):
        k = cache_key(f"ex1|{model}|{url}|{i}|{cache_key(ch)}")
        v = cache.get(k)
        if v is None:
            print(f"  [{url}] chunk {i+1}/{len(chunks)} ({len(ch)} ch) ...", flush=True)
            v = call_llm(EXTRACT_PROMPT + ch, model)
            cache.put(k, v)
            changed = True
        outs.append(v)
    joined = "\n".join(outs)
    if len(chunks) > 1 and not joined.startswith("__LLM_FAIL__"):
        k = cache_key(f"ex2|{model}|{url}|{cache_key(joined)}")
        v = cache.get(k)
        if v is None:
            print(f"  [{url}] merge {len(chunks)} chunks ...", flush=True)
            v = call_llm(MERGE_PROMPT + joined, model, max_tokens=12000)
            cache.put(k, v)
        joined = v
    dest = NOTES / (rec["file"].replace(".json", ".md"))
    header = f"# {url}\nTITLE: {rec.get('title','')}\nSRC_LEN: {len(text)}\n\n"
    dest.write_text(header + joined, encoding="utf-8")
    return f"OK   {url} chunks={len(chunks)} notes={len(joined)}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="auto")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--host", default="")
    args = ap.parse_args()
    recs = records()
    if args.host:
        recs = [r for r in recs if args.host in r["url"]]
    if args.limit:
        recs = recs[: args.limit]
    cache = Cache()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(process, r, cache, args.model, False): r["url"] for r in recs}
        done = 0
        for fut in as_completed(futs):
            url = futs[fut]
            try:
                msg = fut.result()
            except Exception as exc:  # noqa: BLE001
                msg = f"FAIL {url} {type(exc).__name__}: {exc}"
            done += 1
            print(f"[{done}/{len(recs)}] {msg} (+{time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
