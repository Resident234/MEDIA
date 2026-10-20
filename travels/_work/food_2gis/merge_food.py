# -*- coding: utf-8 -*-
"""Слить rows.jsonl и card.jsonl вlabs.jsonl — итоговый массив лабораторий.

usage: python merge_labs.py

Структура строки та же, что в pharmacies.jsonl: id, name, org_name,
address_name, district, lon, lat, is_24x7, card_schedule, phones, websites,
emails, messengers, socials, apps, url_2gis, rating, review_count, rubrics,
sources. Отличие — метка `is_lab` вместо `is_apteka`.
"""
import io
import json
import os
import re
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = os.path.join(HERE, "rows.jsonl")
CARD = os.path.join(HERE, "card.jsonl")
OUT = os.path.join(HERE, "food.jsonl")

CONTACT_BUCKETS = {
    "phone": "phones",
    "siteweb": "websites",
    "website": "websites",
    "url": "websites",
    "email": "emails",
    "whatsapp": "messengers",
    "viber": "messengers",
    "telegram": "messengers",
    "instagram": "socials",
    "facebook": "socials",
    "vkontakte": "socials",
    "ok": "socials",
    "twitter": "socials",
    "youtube": "socials",
}


def load_rows():
    out = {}
    if not os.path.exists(ROWS):
        return out
    for line in io.open(ROWS, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        iid = str(r.get("id"))
        if iid:
            out[iid] = r
    return out


def load_cards(path):
    out = {}
    if not os.path.exists(path):
        return out
    for line in io.open(path, encoding="utf-8"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not rec.get("ok"):
            continue
        iid = str(rec.get("id"))
        if iid and iid not in out:
            out[iid] = rec
    return out


def bucketize(contacts):
    buckets = {"phones": [], "websites": [], "emails": [],
               "messengers": [], "socials": []}
    for c in contacts or []:
        t = (c.get("type") or "").lower()
        bkey = CONTACT_BUCKETS.get(t)
        if not bkey:
            continue
        val = c.get("value") or c.get("url") or c.get("text")
        if val and val not in buckets[bkey]:
            buckets[bkey].append(val)
    return buckets


def merge(rows, cards):
    out = []
    for iid, r in rows.items():
        card = cards.get(iid) or {}
        b = bucketize(card.get("contacts"))
        rec = dict(r)
        rec["card_ok"] = bool(card)
        rec["card_schedule"] = card.get("schedule")
        rec["card_is_24x7"] = card.get("is_24x7")
        rec["card_name"] = card.get("ssr_name") or card.get("name")
        rec["org_name"] = rec.get("org_name") or card.get("org_name")
        rec.update(b)
        rec["apps"] = card.get("apps") or []
        # Рейтинг/отзывы с карточки важнее пустых значений из выдачи.
        if card.get("org_rating") is not None:
            rec["rating"] = card.get("org_rating")
        if card.get("org_review_count") is not None:
            rec["review_count"] = card.get("org_review_count")
        if card.get("address_name") and not rec.get("address_name"):
            rec["address_name"] = card.get("address_name")
        rec.setdefault("sources", []).append("gis_ssr")
        if card:
            rec["sources"].append("gis_card")
        out.append(rec)
    return out


def summarize(food):
    food_rows = [r for r in food if r.get("is_food")]
    networks = Counter()
    for r in food_rows:
        if r.get("org_name"):
            networks[r["org_name"]] += 1
    districts = Counter((r.get("district") or u"?") for r in food_rows)
    hours_24 = sum(1 for r in food_rows
                   if r.get("is_24x7") or r.get("card_is_24x7"))
    with_site = sum(1 for r in food_rows if r.get("websites"))
    with_app = sum(1 for r in food_rows if r.get("apps"))
    with_phone = sum(1 for r in food_rows if r.get("phones"))
    with_sched = sum(1 for r in food_rows if r.get("card_schedule"))
    with_socials = sum(1 for r in food_rows if r.get("socials"))
    hi_rating = sum(1 for r in food_rows
                    if (r.get("rating") or 0) >= 4)
    print("food rows:", len(food_rows), "of", len(food))
    print("rating>=4:", hi_rating)
    print("districts:", json.dumps(dict(districts), ensure_ascii=True))
    print("top networks (>=2):",
          json.dumps([{"n": k, "c": v} for k, v in networks.most_common(20)
                      if v >= 2], ensure_ascii=True))
    print("fields: 24x7=%d sched=%d phone=%d site=%d app=%d socials=%d" % (
        hours_24, with_sched, with_phone, with_site, with_app, with_socials))
    return food_rows


def main():
    rows = load_rows()
    cards = load_cards(CARD)
    merged = merge(rows, cards)
    food_rows = summarize(merged)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        for r in merged:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("wrote:", os.path.basename(OUT), len(merged))


if __name__ == "__main__":
    main()
