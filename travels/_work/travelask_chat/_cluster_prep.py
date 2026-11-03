# -*- coding: utf-8 -*-
"""Подготовка корпуса к кластеризации: отбираем сообщения, которые задают тему.

Правило отбора: сообщение не является ответом (reply_to пусто), в нём есть знак
вопроса или оно длиннее 90 символов, это не служебный текст чата (правила,
реклама каналов, поздравления) и не рассылка-шаблон (одно и то же начало текста
встречается в корпусе 5 раз и чаще). Результат — _topics_pool.jsonl с полями id,
date, text, _boiler_excluded.jsonl с id шаблонных сообщений и _topics_prep.txt
со статистикой.
"""
import io
import json
import os
import re
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
MSGS = os.path.join(HERE, "messages.jsonl")
POOL = os.path.join(HERE, "_topics_pool.jsonl")
BOILER = os.path.join(HERE, "_boiler_excluded.jsonl")
STATS = os.path.join(HERE, "_topics_prep.txt")

# служебное, что пишут админы и боты
ADMIN = re.compile(
    u"(?i)(вам в личку могут писать|DariaAdmin|Daria_admin|рады сообщить|"
    u"напоминаем о наших|подписывайся|канал.?travelask|чат \"|правила чата|"
    u"@vitkozlov|объявлени|вакансии в чат|заявку на|кнопку ответить|"
    u"цитируемое сообщение|сдвиньте|коротко о правилах|добро пожаловать|"
    u"не флуди|зовем на помощь|здесь обсуждаем|правилах общения)")
GREET = re.compile(u"(?i)^(здравствуйте|добрый день|доброе утро|всем привет|"
                   u"привет|дорогие|уважаемые|ассаламу|салам|hello|hi)[\\s,.!]")


def load():
    rows = []
    with io.open(MSGS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def norm(s):
    s = (s or u"").lower().replace(u"\u0451", u"е")
    return re.sub(u"[^a-zа-я0-9]+", u" ", s).strip()


def boiler_prefixes(rows, n=120, min_repeat=5):
    """начала текстов, которые повторяются как рассылка: реклама, правила, боты"""
    c = Counter(norm(r.get("text"))[:n] for r in rows if r.get("text"))
    return set(k for k, v in c.items() if v >= min_repeat and len(k) >= 40)


def main():
    rows = load()
    boiler = boiler_prefixes(rows)
    out = []
    drop_admin = drop_short = drop_boiler = 0
    excluded = []
    for r in rows:
        t = (r.get("text") or u"").strip()
        if r.get("reply_to"):
            continue
        if ADMIN.search(t):
            drop_admin += 1
            continue
        has_q = u"?" in t or u"？" in t
        if not has_q and len(t) < 90:
            drop_short += 1
            continue
        if len(t) < 25:
            drop_short += 1
            continue
        if norm(t)[:120] in boiler:
            drop_boiler += 1
            excluded.append({"id": r["id"], "date": r.get("date"),
                             "text": t[:200]})
            continue
        out.append({"id": r["id"], "date": r.get("date"),
                    "author": r.get("author"), "text": t[:700],
                    "greet": 1 if GREET.match(t) else 0})
    with io.open(POOL, "w", encoding="utf-8", newline=u"\n") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + u"\n")
    with io.open(BOILER, "w", encoding="utf-8", newline=u"\n") as f:
        for r in excluded:
            f.write(json.dumps(r, ensure_ascii=False) + u"\n")

    lens = sorted(len(r["text"]) for r in out)
    years = Counter()
    for r in out:
        m = re.search(u"(\\d{4})", r["date"] or u"")
        years[m.group(1) if m else u"??"] += 1
    lines = [
        u"messages total: %d" % len(rows),
        u"topic-defining: %d" % len(out),
        u"dropped as admin/bot: %d" % drop_admin,
        u"dropped as template/broadcast: %d (%d шаблонов)" % (drop_boiler,
                                                              len(boiler)),
        u"dropped as too short/answer-like: %d" % drop_short,
        u"median len: %d, p90: %d, max: %d" % (
            lens[len(lens) // 2], lens[int(len(lens) * 0.9)], lens[-1]),
        u"by year: " + u", ".join(u"%s=%d" % kv for kv in sorted(years.items())),
        u"with greeting: %d" % sum(r["greet"] for r in out),
    ]
    io.open(STATS, "w", encoding="utf-8", newline=u"\n").write(u"\n".join(lines))
    print("topic-defining=%d boiler_dropped=%d" % (len(out), drop_boiler))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
