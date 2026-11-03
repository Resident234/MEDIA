# -*- coding: utf-8 -*-
"""LLM-разметка и извлечение фактов по теме «онлайн-заказы, доставка, посылки».

Режимы:
  classify — метки MP / LOCAL / SVC / TERM / LIMIT / PAY / RISK / AD / NOISE
             для _deliv_cand.jsonl -> _deliv_labels.jsonl (идемпотентно);
  extract  — из помеченных сообщений тянет строки фактов
             #id | KIND | сервис/город | факт -> _deliv_facts.txt.

Запуск: python _deliv_llm.py classify [--limit N]
        python _deliv_llm.py extract  [--limit N]
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
CAND = os.path.join(HERE, "_deliv_cand.jsonl")
LABELS_OUT = os.path.join(HERE, "_deliv_labels.jsonl")
FACTS_OUT = os.path.join(HERE, "_deliv_facts.txt")

MODELS = ["gpt-oss-120b", "agnes-3.0-flash", "agnes-2.5-flash",
          "qwen3.6-27b", "kilo-auto", "nemotron-3.5-lightning"]

LABELS = ("MP", "LOCAL", "SVC", "TERM", "LIMIT", "PAY", "RISK", "AD", "NOISE")
GOOD = ("MP", "LOCAL", "SVC", "TERM", "LIMIT", "PAY", "RISK")

CLASSIFY_PROMPT = u"""Ты разбираешь сообщения русскоязычного чата путешественников
и переезжающих в Таджикистан. Тема — онлайн-заказы товаров и пересылка посылок.

Для каждого сообщения выбери ОДНУ метку по его главной теме:

MP     — заказ с российского или зарубежного маркетплейса/интернет-магазина:
         Wildberries, Ozon, Яндекс.Маркет, AliExpress, Taobao, СП, «как заказать и
         доставить в Таджикистан», работает ли площадка, сроки, оплата.
LOCAL  — местные таджикские площадки и интернет-магазины (Tolvar, Alif Mall,
         Electric.tj, сомонибазар, local-market и т.п.): что есть, как заказывать.
SVC    — конкретный сервис пересылки/доставки грузов и посылок: Боксберри, СДЭК,
         карго, Почтаи АСР, DHL, FedEx, курьерки, «через Ташкент/Черкизово»:
         цены, сроки, как отправить, где отделение, что берут.
TERM   — пункты выдачи и получение: где забрать, адрес, самовывоз, трек-номер,
         уведомление, хранение, как отследить.
LIMIT  — вес, габариты, стоимость и запреты: сколько можно, что нельзя пересылать,
         таможенные лимиты на посылки, досмотр, опись вложения.
PAY    — оплата заказа из-за границы: карта/Мир/наложенный платёж/предоплата,
         как платить посреднику, комиссия за оплату.
RISK   — проблемы и опыт: не пришло, потеряли, разбили, досмотрели, удержали,
         обманули, долго шло, отказали в выдаче.
AD     — реклама сервиса доставки или посредника (самопиар, прайс, призыв писать
         в личку) без ответа на конкретный вопрос.
NOISE  — всё остальное: доставка еды/цветов/воды, «доставьте меня до аэропорта»,
         доставка документов курьером внутри города, билеты, товары без темы
         пересылки, другие страны без связи с Таджикистаном.

Правила:
- Метка по смыслу сообщения, даже если оно короткое и является частью диалога.
- Если сообщение и спрашивает, и приводит опыт — бери RISK только когда опыт
  негативный и конкретный, иначе метку темы.
- Одно сообщение — одна метка.

Ответ строго JSON-массивом пар [номер, "МЕТКА"], без пояснений.
Пример: [[0,"MP"],[1,"NOISE"]]

СООБЩЕНИЯ:
%s
"""

EXTRACT_PROMPT = u"""Ниже сообщения чата про Таджикистан. Тема — онлайн-заказы товаров
и пересылка посылок (международная доставка грузов, почты, карго, пункты выдачи).
Для каждого сообщения, где есть конкретный факт по теме, извлеки факт.
Формат строки строго такой:
#id | KIND | СЕРВИС/ГОРОД | факт

KIND:
MP     — площадка: заказывает ли кто-то с Wildberries/Ozon/AliExpress/местных,
         что можно и что нельзя заказать, как идет;
SVC    — сервис пересылки: название, цена за кг/за посылку, срок, маршрут,
         где принять/получить, что требует;
TERM   — выдача и трекинг: адрес пункта, как забирать, сроки хранения, уведомление;
LIMIT  — ограничения: вес, размер, стоимость, запрещённые позиции, досмотр, опись;
PAY    — оплата: как оплатить зарубежный заказ, наложенный платёж, комиссия;
RISK   — отказ, потеря, порча, задержка, обман, штраф;
PRACT  — бытовой порядок действий: как упаковать, как оформить, какие документы,
         к кому обратиться (конкретика из личного опыта).

Правила:
- Только то, что прямо сказано в сообщении или в его контексте. Не додумывай.
- СЕРВИС/ГОРОД — если назван, иначе «—».
- Факт — короткая фраза до 220 символов, можно цитатой.
- Если факта по теме нет, строку не пиши.
- Не более 25 строк, без заголовков и пояснений.

СООБЩЕНИЯ:
%s
"""

KINDS = ("MP", "SVC", "TERM", "LIMIT", "PAY", "RISK", "PRACT")


def a(s):
    print(s.encode("ascii", "replace").decode("ascii"))


def load_cand():
    rows = []
    with io.open(CAND, encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    rows.sort(key=lambda r: r["id"])
    return rows


def load_labels():
    done = {}
    if not os.path.exists(LABELS_OUT):
        return done
    with io.open(LABELS_OUT, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            done[r["id"]] = r["label"]
    return done


def fmt(r, num, max_text=650):
    t = re.sub(r"\s+", u" ", r.get("text") or u"")[:max_text]
    rt = re.sub(r"\s+", u" ", r.get("reply_text") or u"")[:200]
    tail = u" | в ответ на: " + rt if rt else u""
    return u"%d. [%s] %s: %s%s" % (num, r.get("date") or u"?",
                                   r.get("author") or u"?", t, tail)


def parse_labels(text, n):
    arr = R.last_json_array(text)
    out = {}
    if arr:
        for pair in arr:
            try:
                idx = int(pair[0])
                lab = str(pair[1]).strip().upper()
            except (TypeError, ValueError, IndexError):
                continue
            if lab in LABELS and 0 <= idx < n:
                out[idx] = lab
        return out
    for k, v in re.findall(r"(\d{1,4})\W{0,6}(%s)\b" % u"|".join(LABELS),
                           text, re.I):
        k = int(k)
        if 0 <= k < n and v.upper() in LABELS:
            out[k] = v.upper()
    return out


def run_classify(pool, rows, out_f, lock):
    lines = [fmt(r, i) for i, r in enumerate(rows)]
    used = pool.pick()
    try:
        txt = R.call(used, CLASSIFY_PROMPT % u"\n".join(lines),
                     max_tokens=2500, tries=1)
    except RuntimeError as e:
        pool.fail(used, 60)
        with lock:
            for r in rows:
                out_f.write(json.dumps({"id": r["id"], "label": u"UNPARSED",
                                       "model": u"err"}, ensure_ascii=False) + u"\n")
            out_f.flush()
        return 0, len(rows)
    got = parse_labels(txt, len(rows))
    if not got:
        pool.fail(used, 20)
    with lock:
        for i, r in enumerate(rows):
            out_f.write(json.dumps({"id": r["id"],
                                    "label": got.get(i, u"UNPARSED"),
                                    "model": used}, ensure_ascii=False) + u"\n")
        out_f.flush()
    return len(got), len(rows)


def cmd_classify(batch=20, workers=4, limit=0):
    rows = load_cand()
    done = load_labels()
    todo = [r for r in rows if done.get(r["id"]) in (None, u"UNPARSED")]
    if limit:
        todo = todo[:limit]
    a("classify: cand=%d done=%d todo=%d" % (len(rows), len(done), len(todo)))
    batches = [todo[i:i + batch] for i in range(0, len(todo), batch)]
    lock = threading.Lock()
    pool = R.Pool(MODELS, interval=1.0)
    mode = "a" if done else "w"
    with io.open(LABELS_OUT, mode, encoding="utf-8", newline=u"\n") as out_f:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            res = list(ex.map(lambda b: run_classify(pool, b, out_f, lock),
                              batches))
    a("labeled now: %d/%d" % (sum(x[0] for x in res), sum(x[1] for x in res)))
    c = Counter()
    for line in io.open(LABELS_OUT, encoding="utf-8"):
        try:
            c[json.loads(line)["label"]] += 1
        except ValueError:
            pass
    a("labels: " + u", ".join(u"%s=%d" % kv for kv in c.most_common()))
    return 0


def load_good(labels_wanted=None):
    labels = load_labels()
    rows = []
    for r in load_cand():
        lab = labels.get(r["id"])
        if labels_wanted:
            if lab in labels_wanted:
                rows.append(r)
        elif lab in GOOD:
            rows.append(r)
    return rows


def fmt_ext(r):
    t = re.sub(r"\s+", u" ", r.get("text") or u"")[:900]
    rt = re.sub(r"\s+", u" ", r.get("reply_text") or u"")[:250]
    tail = u" | в ответ на: " + rt if rt else u""
    return u"#%d [%s] %s: %s%s" % (r["id"], r.get("date") or u"?",
                                   r.get("author") or u"?", t, tail)


def run_extract(pool, rows, out_f, lock):
    lines = [fmt_ext(r) for r in rows]
    valid = set(r["id"] for r in rows)
    used = pool.pick()
    try:
        txt = R.call(used, EXTRACT_PROMPT % u"\n".join(lines),
                     max_tokens=3000, tries=1)
    except RuntimeError:
        pool.fail(used, 60)
        return 0
    good = []
    for ln in txt.splitlines():
        m = re.match(r"\s*#(\d+)\s*\|\s*([A-Z]+)\s*\|\s*([^|]*)\|[ ]?(.*)", ln)
        if not m:
            continue
        mid = int(m.group(1))
        kind = m.group(2)
        if mid not in valid or kind not in KINDS:
            continue
        fact = m.group(4).strip()
        if len(fact) < 12:
            continue
        good.append(u"#%d | %s | %s | %s" % (mid, kind, m.group(3).strip(), fact))
    if not good:
        pool.fail(used, 20)
    with lock:
        for ln in good:
            out_f.write(ln + u"\n")
        out_f.flush()
    return len(good)


def cmd_extract(batch=12, workers=4, limit=0, from_id=0, out_path=None):
    rows = load_good()
    if from_id:
        rows = [r for r in rows if r["id"] >= from_id]
    if limit:
        rows = rows[:limit]
    out_path = out_path or FACTS_OUT
    a("extract: labeled-good=%d -> %s" % (len(rows),
                                          os.path.basename(out_path)))
    batches = [rows[i:i + batch] for i in range(0, len(rows), batch)]
    lock = threading.Lock()
    pool = R.Pool(MODELS, interval=1.0)
    with io.open(out_path, "w", encoding="utf-8", newline=u"\n") as out_f:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            res = list(ex.map(lambda b: run_extract(pool, b, out_f, lock), batches))
    a("facts written: %d" % sum(res))
    c = Counter()
    for line in io.open(out_path, encoding="utf-8"):
        p = line.split(u"|")
        if len(p) > 2:
            c[p[1].strip()] += 1
    a("kinds: " + u", ".join(u"%s=%d" % kv for kv in c.most_common()))
    return 0


def main():
    if len(sys.argv) < 2:
        a("usage: _deliv_llm.py classify|extract [--limit N]")
        return 2
    cmd = sys.argv[1]
    limit = 0
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    from_id = 0
    if "--from-id" in sys.argv:
        from_id = int(sys.argv[sys.argv.index("--from-id") + 1])
    out_path = None
    if "--out" in sys.argv:
        out_path = sys.argv[sys.argv.index("--out") + 1]
        if not os.path.isabs(out_path):
            out_path = os.path.join(HERE, out_path)
    if cmd == "classify":
        return cmd_classify(limit=limit)
    if cmd == "extract":
        return cmd_extract(limit=limit, from_id=from_id, out_path=out_path)
    a("unknown cmd")
    return 2


if __name__ == "__main__":
    sys.exit(main())
