from __future__ import annotations

import json
from pathlib import Path

import analyze as A

BASE = Path(__file__).resolve().parent
RAW = BASE / "raw"
OUT = BASE / "regions.json"

PROMPT = """Ниже — началa статей (travel-блоги) о Таджикистане. Для каждой определи ОДНО короткое название города или региона, которому посвящён текст.

Возможные варианты (используй их, если подходит):
Душанбе; Гиссар и Турсунзаде; Дорога Душанбе-Худжанд (Айни, Анзоб); Худжанд; Согд: Истаравшан, Ура-Тюбе, Кайраккум, Исфара, Канибадам;
Пенджикент и Зарафшан; Ягноб и Фанские горы; Искандеркуль; Дорога на Памир: Гарм, Дарваз, Ванч, Калаи-Хумб; Бадахшан: Хорог, Рощан, Шугнан, Ишкошим, Вахан, Зоркуль, Мургаб, Памирский тракт;
Хатлон: Бохтар (Курган-Тюбе), Куляб, Шаартуз, Вахда; Нурек; Практика: въезд, деньги, быт; Прочее

Ответ: строго по одной строке на статью в формате
URL | Название

Список статей:
"""


def main() -> None:
    items = []
    for f in sorted(RAW.glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        text = " ".join(rec["text"][:700].split())
        if len(text) < 40:
            continue
        items.append(f"{rec['url']} :: {text}")
    cache = A.Cache()
    res = {}
    if OUT.exists():
        res = json.loads(OUT.read_text(encoding="utf-8"))
    batch = 12
    for i in range(0, len(items), batch):
        part = items[i : i + batch]
        prompt = PROMPT + "\n".join(part)
        out = A.call_llm(prompt, "auto", max_tokens=4000)
        for line in out.splitlines():
            if "|" in line:
                u, _, r = line.partition("|")
                u = u.strip().lstrip("-[*0123456789. ").strip()
                if u.startswith("http"):
                    res[u] = r.strip()
        print(f"batch {i//batch+1}: total mapped {len(res)}", flush=True)
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    unmapped = [x.split(" :: ")[0] for x in items if x.split(" :: ")[0] not in res]
    print("unmapped:", len(unmapped), unmapped[:5])


if __name__ == "__main__":
    main()
