# -*- coding: utf-8 -*-
"""Слить rows.jsonl (Душанбе, аптеки из SSR-поиска) с card.jsonl (карточки).

usage: python merge_pharma.py

На выходе:
  - `pharmacies.jsonl` — по аптеке на строку: id, name, org_name (сеть),
    address_name, district, lon, lat, is_24x7, schedule (текст),
    websites (список URL), phones, messengers (whatsapp/telegram/viber),
    socials, apps (App Store/Google Play/RuStore/AppGallery), url_2gis,
    rating, review_count, sources (`gis_ssr`, `gis_card`, `shops_reuse`).
  - сводка по сетям/районам/часам в консоли (ASCII), чтобы понимать,
    что показывать в прозе раздела.

Card-филд `contacts` — список {type, text, value, url}, где `type` из
{phone, website, email, telegram, whatsapp, viber, instagram, ok, facebook,
vkontakte}. Apps в card.jsonl уже отобраны регуляркой по JSON-контейнеру.

Несколько id могут принадлежать одной сети: `org_name` из rows даёт имя,
`branch_count` — сколько у неё точек (по данным 2ГИС). Отдельные источники
(173 аптеки из прошлой фазы покупок, уже сидящие в shops_2gis/ssr_cards.jsonl)
подмешиваются через `card.jsonl` (seed_from_shops).
"""
import io
import json
import os
import re
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = os.path.join(HERE, "rows.jsonl")
CARD = os.path.join(HERE, "card.jsonl")
SHOPS_CARD = os.path.join(HERE, "..", "shops_2gis", "ssr_cards.jsonl")
OUT = os.path.join(HERE, "pharmacies.jsonl")

PHONE_RE = re.compile(r"^\+?\d[\d\s\-().]{5,}$")
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


def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


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
        if not iid:
            continue
        out[iid] = r
    return out


def load_cards(paths):
    """Слить card.jsonl из обеих фаз: id -> rec."""
    out = {}
    for p in paths:
        if not os.path.exists(p):
            continue
        for line in io.open(p, encoding="utf-8"):
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
    """Объединённая карта аптек: только те id, которые реально аптеки."""
    out = []
    for iid, r in rows.items():
        if not r.get("is_apteka"):
            # всё-таки добавим, но поместим ниже (в rows бывают соседние карточки)
            pass
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
        rec.setdefault("sources", []).append("gis_ssr")
        if card:
            rec["sources"].append("gis_card")
        out.append(rec)
    # карточки из shops_2gis, но не попавшие в rows: это 173 pharmacy-name
    for iid, c in cards.items():
        if iid in rows:
            continue
        if not any(k in (c.get("name") or c.get("ssr_name") or "").lower()
                   for k in (u"аптек", u"дорух", u"фарм")):
            continue
        b = bucketize(c.get("contacts"))
        rec = {"id": iid, "name": c.get("ssr_name") or c.get("name"),
               "org_name": c.get("org_name"),
               "card_schedule": c.get("schedule"),
               "card_is_24x7": c.get("is_24x7"), "card_ok": True,
               "url_2gis": "https://2gis.tj/dushanbe/firm/%s" % iid}
        rec.update(b)
        rec["apps"] = c.get("apps") or []
        rec["sources"] = ["shops_reuse"]
        out.append(rec)
    return out


def is_apteka(rec):
    nm = ((rec.get("name") or "") + " " + (rec.get("card_name") or "") +
          " " + (rec.get("org_name") or "")).lower()
    return any(k in nm for k in (u"аптек", u"дорух", u"фарм", u"apteka",
                                  u"pharmacy")) or u"Аптеки" in (rec.get("rubrics") or [])


def summarize(rows):
    """ASCII-сводка: сети, часы, районы, покрытие полей — для prose-блока."""
    ap = [r for r in rows if is_apteka(r)]
    networks = Counter()
    for r in ap:
        if r.get("org_name"):
            networks[r["org_name"]] += 1
    districts = Counter((r.get("district") or u"?") for r in ap)
    hours_24 = sum(1 for r in ap if r.get("is_24x7") or r.get("card_is_24x7"))
    with_site = sum(1 for r in ap if r.get("websites"))
    with_app = sum(1 for r in ap if r.get("apps"))
    with_phone = sum(1 for r in ap if r.get("phones"))
    with_sched = sum(1 for r in ap if r.get("card_schedule"))
    print("apteka rows:", len(ap))
    print("districts:", json.dumps(dict(districts), ensure_ascii=True))
    print("top networks (>=3):",
          json.dumps([{"n": k, "c": v} for k, v in networks.most_common(20)
                      if v >= 3], ensure_ascii=True))
    print("fields: 24x7=%d sched=%d phone=%d site=%d app=%d" % (
        hours_24, with_sched, with_phone, with_site, with_app))
    return ap


def main():
    rows = load_rows()
    cards = load_cards([CARD, SHOPS_CARD])
    merged = merge(rows, cards)
    ap = summarize(merged)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        for r in merged:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("wrote:", os.path.basename(OUT), len(merged))


if __name__ == "__main__":
    main()
