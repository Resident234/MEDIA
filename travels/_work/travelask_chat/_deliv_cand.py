# -*- coding: utf-8 -*-
"""Отбор сообщений чата по теме «онлайн-заказы, доставка и пересылка посылок».

Широкий словарь + контекст (ответы редко повторяют слово «посылка»). Точность
добирает LLM в _deliv_llm.py. Выход: _deliv_cand.jsonl (id, date, author, text,
reply_to, reply_text, before/after, groups).
"""
import io
import json
import os
import re
from collections import Counter, OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(HERE, "messages.jsonl")
OUT = os.path.join(HERE, "_deliv_cand.jsonl")
CONTEXT = 2

GROUPS = OrderedDict([
    # площадки и заказы онлайн
    ("marketplace", r"маркетплейс|wildberries|вайлдбер|ozon|озон|яндекс\s*маркет|"
                    r"алиэкспресс|aliexpress|таобао|taobao|pinduoduo|temu|amazon|"
                    r"caspi|электрик\s*тдж|alif\s*mall|алиф\s*мол|ishop|shop\.tj|"
                    r"somon\.tj|farsh|толвар"),
    ("order", r"заказ[а-я]*\s+(товар|с\s+сайт|из\s+росси|с\s+кит|на\s+маркет|на\s+wild|"
              r"на\s+озон)|как\s+заказать|заказыва[а-я]*|можно\s+заказ|доставка\s+товар|"
              r"заказ[а-я]*\s+(посылк|из|на\s+сайт)"),
    # сервисы доставки и пересылки
    ("service", r"боксберри|boxberry|сдэк|cdek|курьер|courier|карго|cargo|"
                r"почта[а-я]*\s+(тад|аср|душанбе|росси)|почт[а-я]*\s+аср|"
                r"\bdhl\b|\btnt\b|fedex|федерал|\bups\b|\bems\b|"
                r"деловые\s+линии|\bким\s+(экспресс|груз|доставк)|"
                r"грузов[а-я]*\s+перевозк|междун[а-я]*\s+карго|"
                r"экспр[её]с-?доставк|доставк[а-я]*\s+груза"),
    ("track", r"трек|трекинг|отслеж|извещени|уведомлени[а-я]*\s+о\s+посыл|"
              r"пришл[а-я]*\s+уведомл|почт[а-я]*\s+извещ"),
    ("send", r"отправ[а-я]*\s+(посылк|документ|деньги|из\s+душанбе|в\s+росси|на\s+росси)|"
             r"пересылк|посылк[а-я]*\s+(идт|летит|шли|принял|получ)|"
             r"как\s+отправить|через\s+что\s+отправля"),
    ("tariff", r"стоимость\s+доставк|сколько\s+стоим.*достав|тариф|за\s+килограмм|"
               r"за\s+кг|минимальн[а-я]*\s+вес|оплат[а-я]*\s+за\s+доставк|"
               r"комисси[а-я]*\s+за\s+доставк|доставк[а-я]*\s+(дорого|бесплатн|платн)"),
    ("weight", r"вес[а-я]*\s+(посылк|не\s+превыша|котор|товар)|до\s+50\s+кг|"
               r"50\s+килограмм|1000\s+доллар|оценочн[а-я]*\s+стоимост|"
               r"габарит|объёмн[а-я]*\s+вес|паллет|мест[а-я]*\s+груза"),
    ("ban", r"запрещ[а-я]*\s+к\s+пересыл|нельзя\s+(отправ|пересыл|ввоз)|"
            r"список\s+запрещ|не\s+пропуст[а-я]*\s+таможн|заверну|не\s+отдал|"
            r"изъял[а-я]*\s+таможн|конфиск"),
    ("pack", r"упаков|обрешёт|обрешет|паллет|факт[а-я]*\s+поврежд|бой[а-я]*\s+стекл|"
             r"страховк[а-я]*\s+груз"),
    ("pickup", r"пункт\s+выдач|самовывоз|забрать\s+(посылк|заказ)|выдач[а-я]*\s+посыл|"
               r"интернет-?магазин.{0,30}(выдач|забран|пункт)"),
    ("intermed", r"посредник|выкуп|ретранслятор|склад\s+(в\s+росси|москв|ташкент)|"
                 r"адрес\s+(для\s+доставк|в\s+росси|москв)|доставк[а-я]*\s+через\s+ташкент|"
                 r"собират[а-я]*\s+посылк|отправляют\s+с\s+росси"),
    ("review", r"отзыв\s+на\s+сервис|не\s+довезл|обман|мошенниц|кинул[а-я]*|не\s+пришел|"
               r"так\s+и\s+не\s+приш|потерял[а-я]*\s+посылк|долго\s+идт"),
])

PRE = [(g, re.compile(p, re.I)) for g, p in GROUPS.items()]

# явный шум: доставка еды, доставка в отели как услуга, билеты с доставкой
NOISE = re.compile(
    r"доставк[а-я]*\s+(еды|пицц|суши|блюда|продукт.{0,12}(из\s+магазин)?|"
    r"заказ.{0,15}(еда|кафе|ресторан))|yandex\s+eda|гастронум|sama|zelenskiy|"
    r"доставк[а-я]*\s+(воды|газа|кислород)", re.I)

BOT_AD = re.compile(r"карты\.travelask|удаленное открытие|кешбэк-ссылк", re.I)


def a(s):
    print(s.encode("ascii", "replace").decode("ascii"))


def main():
    rows = []
    with io.open(IN, encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    rows.sort(key=lambda r: r["id"])
    by_id = {r["id"]: r for r in rows}
    idx = {r["id"]: i for i, r in enumerate(rows)}

    per = {}
    for r in rows:
        t = r.get("text") or u""
        if len(t) < 6:
            continue
        if (r.get("author") or u"") in ("travelask_help_bot",
                                        "travelask_moderator_") and BOT_AD.search(t):
            continue
        gs = [g for g, pat in PRE if pat.search(t)]
        if not gs:
            continue
        # «доставка» в одиночку — шумно: еда, вода, люди просят привезти себя
        if gs == ["tariff"] or gs in (["order"], ["weight"], ["pack"]):
            if not re.search(r"посылк|пересылк|маркетплейс|заказ|товар|доставк[а-я]*\s+"
                             r"(из|с\s+|товар)", t, re.I):
                continue
        if NOISE.search(t) and not re.search(
                r"посылк|пересылк|маркетплейс|wildberries|озон|карго|сдэк|боксберри",
                t, re.I):
            continue
        per[r["id"]] = gs

    a("messages: %d" % len(rows))
    a("hits: %d" % len(per))
    gh = Counter()
    for i in per:
        for g in per[i]:
            gh[g] += 1
    a("groups: " + u", ".join(u"%s=%d" % kv for kv in gh.most_common()))

    out = io.open(OUT, "w", encoding="utf-8", newline=u"\n")
    for r in rows:
        if r["id"] not in per:
            continue
        i = idx[r["id"]]
        before = rows[max(0, i - CONTEXT):i]
        after = rows[i + 1:i + 1 + CONTEXT]
        rt = r.get("reply_to")
        reply = by_id.get(rt) if rt else None
        rec = {
            "id": r["id"], "date": r.get("date", ""), "author": r.get("author", ""),
            "text": r["text"], "reply_to": rt,
            "reply_text": (reply.get("text", "")[:500] if reply else ""),
            "groups": per[r["id"]],
            "before": [{"id": b["id"], "author": b.get("author", ""),
                        "date": b.get("date", ""), "text": b["text"]}
                       for b in before],
            "after": [{"id": b["id"], "author": b.get("author", ""),
                       "date": b.get("date", ""), "text": b["text"]}
                      for b in after],
        }
        out.write(json.dumps(rec, ensure_ascii=False) + u"\n")
    out.close()
    years = Counter()
    for i in per:
        m = re.match(r"\d{2}\.\d{2}\.(\d{4})", by_id[i].get("date") or u"")
        years[m.group(1) if m else u"?"] += 1
    a("by year: " + u", ".join(u"%s=%d" % kv for kv in sorted(years.items())))
    a("written: %s" % os.path.basename(OUT))


if __name__ == "__main__":
    main()
