# -*- coding: utf-8 -*-
"""Добор контактов из карточек организаций.

Выдача мелких населённых пунктов (общий поиск по карте) приходит без
телефонов, сайтов и соцсетей — только название, адрес и рейтинг. Карточка
той же организации по тому же HTTP-каналу эти поля отдаёт, поэтому скрипт
идёт по уже найденным объектам и дописывает недостающее в
``lists/zzcards__cards.jsonl`` в том же виде, что и выдача: merge.py
склеивает записи по id и подхватывает поля сам.

usage: python enrich.py [--limit N] [--pause 3]
"""
import argparse
import io
import json
import os
import sys
import time

import yxhttp
from yxd import HOST

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = os.path.join(HERE, "housing_yx.jsonl")
CARDS = os.path.join(HERE, "lists", "zzcards__cards.jsonl")
LOG = os.path.join(HERE, "lists", "enrich.log")

# Поля карточки, которые нужны сборке. workingTime приводим к тексту:
# у карточки рядом лежит готовое «ежедневно, круглосуточно».
KEEP = ("id", "title", "seoname", "type", "country", "coordinates",
        "phones", "urls", "socialLinks", "categories", "ratingData")
MAX_FAIL = 5          # подряд неудач — канал закрылся, выходим
BAN_PAUSE = 120       # пауза после заглушки anti-bot


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line)
    sys.stdout.flush()
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def url_of(row):
    url = row.get("url") or ""
    if "/maps/org/" in url:
        return url
    if row.get("id"):
        return "%s/maps/org/%s/%s/" % (HOST, row.get("seoname") or "x",
                                       row["id"])
    return None


def card(url):
    """(item, status): item — объект карточки, status — list|throttled|empty."""
    body, _ = yxhttp._get(url)
    if body is None:
        return None, "throttled"
    res = yxhttp._results(body)
    if not res:
        return None, "empty"
    for it in res.get("items") or []:
        if isinstance(it, dict) and str(it.get("id")) in url:
            return it, "list"
    items = [i for i in (res.get("items") or [])
             if isinstance(i, dict) and i.get("type") == "business"]
    return (items[0], "list") if items else (None, "empty")


def pack(it):
    rec = {}
    for k in KEEP:
        if it.get(k) not in (None, [], {}, ""):
            rec[k] = it[k]
    rec["type"] = it.get("type") or "business"
    txt = it.get("workingTimeText") or it.get("workingTime")
    if isinstance(txt, str):
        rec["workingTime"] = txt
    return rec


def targets():
    """Объекты, которым не хватает контактов, в порядке файла."""
    rows = []
    with io.open(ROWS, encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not row.get("id"):
                continue
            full = (row.get("phones") and row.get("sites")
                    and (row.get("whatsapp") or row.get("telegram")
                         or row.get("socials")))
            if not full:
                rows.append(row)
    return rows


def done_ids():
    seen = set()
    if not os.path.exists(CARDS):
        return seen
    with io.open(CARDS, encoding="utf-8") as f:
        for line in f:
            try:
                seen.add(str(json.loads(line).get("id")))
            except ValueError:
                continue
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="сколько карточек обработать за запуск (0 — все)")
    ap.add_argument("--pause", type=float, default=3.0,
                    help="пауза между карточками, секунды")
    args = ap.parse_args()

    todo = targets()
    seen = done_ids()
    queue = [r for r in todo if str(r.get("id")) not in seen]
    if args.limit:
        queue = queue[:args.limit]
    log("targets=%d already=%d queue=%d" % (len(todo), len(seen), len(queue)))

    got = phones = sites = socials = fails = 0
    out = io.open(CARDS, "a", encoding="utf-8")
    try:
        for num, row in enumerate(queue, 1):
            url = url_of(row)
            if not url:
                continue
            it, status = card(url)
            if status == "throttled":
                log("throttled on %s, pause %ds" % (row.get("id"), BAN_PAUSE))
                time.sleep(BAN_PAUSE)
                it, status = card(url)
            if status != "list" or not it:
                fails += 1
                log("%d/%d %s -> %s" % (num, len(queue), row.get("id"),
                                        status))
                if fails >= MAX_FAIL:
                    log("channel closed, stop. cards=%d" % got)
                    return 2
                time.sleep(args.pause)
                continue
            fails = 0
            rec = pack(it)
            # Без координат merge не сможет приписать город и назовёт источник
            # именем файла — такие карточки бесполезны.
            if not rec.get("coordinates"):
                log("%d/%d %s -> no coords" % (num, len(queue), row.get("id")))
                time.sleep(args.pause)
                continue
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            got += 1
            phones += int(bool(rec.get("phones")))
            sites += int(bool(rec.get("urls")))
            socials += int(bool(rec.get("socialLinks")))
            if num % 10 == 0 or num == len(queue):
                log("%d/%d %s cards=%d phones=%d sites=%d social=%d" % (
                    num, len(queue), (row.get("name") or "")[:28], got,
                    phones, sites, socials))
            # Раз в полсотни карточек — пауза подольше, чтобы не ловить 429.
            time.sleep(args.pause * 4 if num % 50 == 0 else args.pause)
        log("done. cards=%d phones=%d sites=%d social=%d" % (
            got, phones, sites, socials))
    finally:
        out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
