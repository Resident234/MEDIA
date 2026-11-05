# -*- coding: utf-8 -*-
"""Stage C: нормализация и слияние имён сущностей в канонические папки.

Берёт из ledger (text_class.jsonl и, если есть, vision_class.jsonl) все
распознанные собственными имена и просит LLM склеить явные варианты ОДНОЙ и
той же сущности (падеж, "банк X" vs "X банк", латиница/кириллица, лишние
слова). Разные объекты не сливает. Результат: entity_groups.json —
    {"alias_norm": "<display_name для папки>", ...}
"""
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join("..", "travelask_chat")))
import triage  # noqa: E402
from classify_text import call, last_json_array  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = [m.strip() for m in os.environ.get(
    "LLM_MODELS", "gpt-oss-20b,auto").split(",") if m.strip()]

# служебные «сущности», не достойные отдельной папки
BLOCK = {"travelask"}

MERGE_PROMPT = u"""Ты группируешь названия сущностей (места, отели, заведения,
рынки, достопримечательности, города, сервисы/приложения) из туристического
чата о Таджикистане в канонические сущности.

СЛИВАЙ только явные варианты одной и той же сущности: разный падеж/число,
«банк X» vs «X банк», лишние слова-описания, латиница vs кириллица одного
имени, опечатки. НЕ сливай разные реальные объекты, даже похожие по роду
(два разных отеля — две сущности). Названия городов/регионов остаются
самостоятельными сущностями.

Вход — список названий. Ответ — строго JSON-массив без текста вокруг, каждый
объект: {"display": "<короткое имя для папки>", "members": ["точное название
из входа", ...]}. В members клади только строки из входа, ничего не выдумывай.

%s
"""


def norm(s):
    s = (s or u"").strip().lower()
    s = re.sub(r"[\"'`’‘ʼ]", u"", s)
    s = re.sub(r"[^\w\s\-]", u" ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", u" ", s).strip()
    return s


def collect_entities():
    ents = {}   # norm -> representative raw
    freq = {}   # norm -> photo count
    files = [os.path.join(HERE, "text_class.jsonl"),
             os.path.join(HERE, "vision_class.jsonl")]
    for fp in files:
        if not os.path.exists(fp):
            continue
        for line in io.open(fp, encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("named") and (r.get("entity") or "").strip():
                k = norm(r["entity"])
                if k in BLOCK:
                    continue
                ents.setdefault(k, r["entity"].strip())
                freq[k] = freq.get(k, 0) + 1
    return ents, freq  # norm -> representative raw


def merge_pass(ents, freq):
    """Полный self-map по всем сущностям + LLM-склейка только повторяющихся
    имён (freq>=2) small-batch'ами, чтобы JSON не обрезался."""
    pool = list(MODELS)
    mapping = dict((k, v) for k, v in ents.items())  # по умолчанию сами себе
    # повторяющиеся имена — кандидаты на слияние вариантов одного объекта
    cand = sorted((v for k, v in ents.items() if freq[k] >= 2), key=str.lower)
    print("  merge candidates (freq>=2):", len(cand), "of", len(ents))
    B = 30
    nb = (len(cand) + B - 1) // B
    for i in range(0, len(cand), B):
        batch = cand[i:i + B]
        prompt = MERGE_PROMPT % u"\n".join(u"- " + n for n in batch)
        arr = None
        for _ in range(6):
            try:
                arr = last_json_array(call(pool[0], prompt, max_tokens=2500, tries=1))
                if arr:
                    break
            except Exception:  # noqa: BLE001
                pass
            pool = pool[1:] + pool[:1]
            time.sleep(4)
        applied = 0
        for grp in (arr or []):
            if not isinstance(grp, dict):
                continue
            disp = (grp.get("display") or u"").strip()
            mem = grp.get("members") or []
            if not disp or not isinstance(mem, list) or len(mem) < 2:
                continue  # слияние только из >=2 членов
            for m in mem:
                if isinstance(m, str) and norm(m) in mapping:
                    mapping[norm(m)] = disp
                    applied += 1
        print("  merged batch %d/%d (pool=%s, groups=%d, applied=%d)"
              % (i // B + 1, nb, pool[0], len(arr or []), applied))
    return mapping


def main():
    ents, freq = collect_entities()
    print("distinct named entities:", len(ents))
    mapping = merge_pass(ents, freq)
    io.open(os.path.join(HERE, "entity_groups.json"), "w", encoding="utf-8",
            newline=u"\n").write(json.dumps(mapping, ensure_ascii=False, indent=1))
    # посчитать фото по итоговым папкам
    folder_photos = {}
    for k, d in mapping.items():
        folder_photos[d] = folder_photos.get(d, 0) + freq.get(k, 0)
    print("canonical folders:", len(folder_photos))
    for d, c in sorted(folder_photos.items(), key=lambda x: -x[1])[:25]:
        print("  %4d  %s" % (c, d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
