# -*- coding: utf-8 -*-
"""Целевая LLM-выжимка: ОТПРАВКА ИЗ Таджикистана (прежде всего в Россию).

Отбираем из всего корпуса сообщения-«отправители» (глагол отправки + российская
цель или таджикское происхождение), растягиваем их диалогами (родитель+ответы)
и гоняем через модель, доставая структурированные факты:
сервис, категория товара, цена/лимит, процедура, риск.

Строка факта:  #id | KIND | СЕРВИС | КАТЕГОРИЯ | ДЕТАЛЬ
KIND: SVC|COST|LIMIT|CAT|PROC|RISK

Запуск: python _sendru_llm.py  [--limit N] [--workers K]
"""
import io
import json
import os
import re
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import _llm_review_62 as R

HERE = os.path.dirname(os.path.abspath(__file__))
MSGS = os.path.join(HERE, "messages.jsonl")
OUT = os.path.join(HERE, "_sendru_facts.txt")

MODELS = ["gpt-oss-120b", "agnes-3.0-flash", "agnes-2.5-flash",
          "qwen3.6-27b", "kilo-auto", "nemotron-3.5-lightning"]

SEND = re.compile(u"(?i)(отправ|пересл|отослал|отосла|вывез|перешл|в руки|попутк"
                  u"|не принимают письма|не отправляет)")
RU = re.compile(u"(?i)(в росси|в рф|в москв|в питер|в санкт|в спб|в казан|в new"
                u"|в Новосиб|в Екатеринбург|обратно в|в петербург|в уфу|в краснояр"
                u"|в самар|в воронеж|в ростов|в казах|в армен|в европ|в герман)")
TJ = re.compile(u"(?i)(из душанбе|из худжанд|из бохтар|из таджик|из РТ|из канибадам"
                u"|из куляб|из гарм|из бустон|из турсунза|из регар|из исфара|из пенджик"
                u"|из пенджикент|из нурек|из вахдат|из страны|из Таджикистана)")

KINDS = ("SVC", "COST", "LIMIT", "CAT", "PROC", "RISK")

PROMPT = u"""Ты разбираешь сообщения русскоязычного чата про Таджикистан.
Нужен ОДНЁ аспект: ОТПРАВКА ГРУЗОВ/ПОСЫЛОК/ДОКУМЕНТОВ ИЗ ТАДЖИКИСТАНА наружу,
в первую очередь в Россию (но также Казахстан, Армению, Европу).
Получение/заказ товаров ВНУТРЬ Таджикистана сюда НЕ относится — его игнорируй.

Для каждого сообщения, где есть конкретный факт по отправке НАРУЖУ, извлеки факт.
Формат строки строго:
#id | KIND | СЕРВИС | КАТЕГОРИЯ | ДЕТАЛЬ

KIND:
SVC    — чем отправляют (Почтаи Аср, Почтаи тоҷик/гос.почта, DHL, FedEx, TNT, EMS,
         СДЭК, BorEx, карго, «в руки в аэропорту», авиакомпания, посредник);
COST   — сколько стоит отправка (за кг, за посылку, за документы, комиссия);
LIMIT  — ограничения веса/размера/стоимости, что досматривают, опись;
CAT    — категорию товаров: что берут / что НЕ берут / что конфискуют
         (документы, одежда, еда, электроника, аккумуляторы, лекарства, наличные);
PROC   — процедура: как оформить, какие документы, куда принести, сроки;
RISK   — что пошло не так (не приняли, вернули, потеряли, задержали, обманули).

Правила:
- Только то, что прямо сказано в сообщении или в его показанном контексте. Не додумывай.
- СЕРВИС / КАТЕГОРИЯ — если названы, иначе «—».
- ДЕТАЛЬ — короткая фраза до 200 символов, можно цитатой.
- Если факта про отправку НАРУЖУ нет — строку НЕ пиши.
- Не более 30 строк, без заголовков и пояснений.

СООБЩЕНИЯ:
%s
"""


def a(s):
    print(s.encode("ascii", "replace").decode("ascii"))


def load_all():
    d = {}
    for line in io.open(MSGS, encoding="utf-8"):
        r = json.loads(line)
        d[r["id"]] = r
    return d


def build_pool():
    msgs = load_all()
    kids = {}
    for r in msgs.values():
        rt = r.get("reply_to")
        if rt in msgs:
            kids.setdefault(rt, []).append(r["id"])
    seeds = set()
    for r in msgs.values():
        t = r.get("text") or u""
        if SEND.search(t) and (RU.search(t) or TJ.search(t)):
            seeds.add(r["id"])
    # расширение диалогами
    pool = set(seeds)
    for i in seeds:
        p = msgs[i].get("reply_to")
        if p in msgs:
            pool.add(p)
        for c in kids.get(i, []):
            pool.add(c)
    a("seeds=%d pool=%d" % (len(seeds), len(pool)))
    return [msgs[i] for i in sorted(pool)], msgs


def fmt(r):
    t = re.sub(r"\s+", u" ", r.get("text") or u"")[:850]
    rt = r.get("reply_to")
    tail = u" | [ответ на #%s]" % rt if rt else u""
    return u"#%d [%s] %s%s: %s" % (r["id"], (r.get("date") or u"?")[:10],
                                   r.get("author") or u"?", tail, t)


def run(pool, rows, out_f, lock):
    lines = u"\n".join(fmt(r) for r in rows)
    valid = set(r["id"] for r in rows)
    good = []
    for attempt in range(5):
        used = pool.pick()
        try:
            txt = R.call(used, PROMPT % lines, max_tokens=3000, tries=1)
        except RuntimeError as exc:
            msg = str(exc)
            pool.fail(used, 120 if u"429" in msg else 40)
            continue
        good = []
        for ln in txt.splitlines():
            m = re.match(
                r"\s*#(\d+)\s*\|\s*([A-Z]+)\s*\|\s*([^|]*)\|\s*([^|]*)\|\s*(.*)", ln)
            if not m:
                continue
            mid, kind = int(m.group(1)), m.group(2)
            if mid not in valid or kind not in KINDS:
                continue
            det = m.group(5).strip()
            if len(det) < 10:
                continue
            good.append(u"#%d | %s | %s | %s | %s"
                        % (mid, kind, m.group(3).strip(), m.group(4).strip(), det))
        if good:
            break
        pool.fail(used, 20)
    if not good:
        return 0
    with lock:
        for ln in good:
            out_f.write(ln + u"\n")
        out_f.flush()
    return len(good)


def main():
    limit = 0
    workers = 4
    batch = 10
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if "--workers" in sys.argv:
        workers = int(sys.argv[sys.argv.index("--workers") + 1])
    rows, _ = build_pool()
    if limit:
        rows = rows[:limit]
    a("to send: %d msgs, batch=%d workers=%d" % (len(rows), batch, workers))
    batches = [rows[i:i + batch] for i in range(0, len(rows), batch)]
    lock = threading.Lock()
    pool = R.Pool(MODELS, interval=1.0)
    with io.open(OUT, "w", encoding="utf-8", newline=u"\n") as out_f:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            res = list(ex.map(lambda b: run(pool, b, out_f, lock), batches))
    a("facts written: %d -> %s" % (sum(res), os.path.basename(OUT)))
    c = Counter()
    ids = set()
    for line in io.open(OUT, encoding="utf-8"):
        p = line.split(u"|")
        if len(p) > 2:
            c[p[1].strip()] += 1
            try:
                ids.add(int(p[0].strip("#\n ")))
            except ValueError:
                pass
    a("kinds: " + u", ".join(u"%s=%d" % kv for kv in c.most_common()))
    a("distinct ids cited: %d" % len(ids))
    return 0


if __name__ == "__main__":
    sys.exit(main())
