# -*- coding: utf-8 -*-
"""Слить rows.jsonl и card.jsonl в housing.jsonl.

usage: python merge_housing.py

Структура строки та же, что в food.jsonl: id, name, org_name, address_name,
district, lon, lat, is_24x7, card_schedule, phones, websites, emails,
messengers, socials, apps, url_2gis, rating, review_count, rubrics, sources.
Метка `is_housing` вместо `is_food`.
"""
import io
import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = os.path.join(HERE, "rows.jsonl")
CARD = os.path.join(HERE, "card.jsonl")
OUT = os.path.join(HERE, "housing.jsonl")

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


def summarize(housing):
    hs = [r for r in housing if r.get("is_housing")]
    networks = Counter()
    for r in hs:
        if r.get("org_name"):
            networks[r["org_name"]] += 1
    districts = Counter((r.get("district") or u"?") for r in hs)
    with_site = sum(1 for r in hs if r.get("websites"))
    with_phone = sum(1 for r in hs if r.get("phones"))
    with_msg = sum(1 for r in hs if r.get("messengers"))
    with_socials = sum(1 for r in hs if r.get("socials"))
    hi_rating = sum(1 for r in hs if (r.get("rating") or 0) >= 4)
    print("housing rows:", len(hs), "of", len(housing))
    print("rating>=4:", hi_rating)
    print("districts:", json.dumps(dict(districts), ensure_ascii=True))
    print("top networks (>=2):",
          json.dumps([{"n": k, "c": v} for k, v in networks.most_common(20)
                      if v >= 2], ensure_ascii=True))
    print("fields: phone=%d site=%d msg=%d socials=%d" % (
        with_phone, with_site, with_msg, with_socials))
    return hs


def main():
    rows = load_rows()
    cards = load_cards(CARD)
    merged = merge(rows, cards)
    summarize(merged)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        for r in merged:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("wrote:", os.path.basename(OUT), len(merged))


if __name__ == "__main__":
    main()
