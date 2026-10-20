# -*- coding: utf-8 -*-
"""Merge items_all.json (API) + ssr_cards.jsonl (web contacts) into one table.

Category buckets follow the раздел 8 request. An item is placed in the FIRST
bucket whose test matches (most specific first); the generic «магазины» tail
catches everything else. Buckets are decided from the API evidence we have:
rubric ids (350 супермаркеты, 12127 гипермаркеты, 112611 ПВЗ, 110333 молҳои
миллӣ, 510 тӯҳфаҳо) and the query words whose tile pass found the card.

Contacts are taken strictly from the card's own SSR container (ssr_shops.py);
website links that go through the 2GIS redirect keep the human-readable
domain from the contact text. Apps (App Store / Google Play / RuStore /
AppGallery) are those found inside the same container.

usage: python aggregate.py
Outputs: aggregate.tsv (all buckets), agg_summary.json (counts + coverage).
"""
import io
import json
import os
from collections import Counter, OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))


def is_provider(r):
    """Интернет-провайдер в выдаче «интернет-магазин».

    2ГИС ищет по словам, и в «интернет-магазины» липнут Babilon-T, Sa-net и
    Tojiktelecom — это поставщики связи, а не онлайн-торговля. В bucket их не
    берём: родовая корзина честнее, чем чужая строка в запрошенной категории.
    """
    names = " ".join((n or "").lower() for n in r["rubric_names"])
    return ("провайдер" in names or "provider" in names
            or "интернет хизматрасонӣ" in names)


BUCKETS = [
    ("базары и рынки", lambda r: bool({"query:базар", "query:бозор", "query:рынок"} & set(r["passes"]))
        or any("бозор" in (n or "").lower() or "рынок" in (n or "").lower() for n in r["rubric_names"])),
    ("ярмарки", lambda r: "query:ярмарка" in r["passes"]),
    ("торговые центры", lambda r: "query:торговый центр" in r["passes"]
        or any("торговый центр" in (n or "").lower() or "савдо маркази" in (n or "").lower() for n in r["rubric_names"])),
    ("гипермаркеты", lambda r: "12127" in r["rubric_ids"] or "query:гипермаркет" in r["passes"]),
    ("супермаркеты", lambda r: "350" in r["rubric_ids"] or "query:супермаркет" in r["passes"]),
    ("пункты выдачи (ПВЗ)", lambda r: "112611" in r["rubric_ids"] or "query:пункт выдачи" in r["passes"]),
    ("интернет-магазины и маркетплейсы", lambda r: bool({"query:интернет-магазин", "query:маркетплейс"} & set(r["passes"])) and not is_provider(r)),
    ("ремёсла и сувениры", lambda r: bool({"110333", "510"} & set(r["rubric_ids"]))
        or bool({"query:ремесла", "query:сувениры"} & set(r["passes"]))),
]
SOCIAL_TYPES = ("instagram", "facebook", "tiktok", "youtube", "ok", "twitter",
                "vk", "odnoklassniki", "pinterest", "linkedin")


def contacts_of(rec):
    out = {"phones": [], "website": [], "email": [], "whatsapp": [],
           "telegram": [], "viber": [], "social": [], "apps": []}
    if not rec:
        return out
    for c in rec.get("contacts") or []:
        t = (c.get("type") or "").lower()
        text = (c.get("text") or "").strip()
        url = (c.get("url") or c.get("value") or "").strip()
        if t == "phone":
            out["phones"].append(text or url)
        elif t == "website":
            out["website"].append(text or url)
        elif t == "email":
            out["email"].append(text or url)
        elif t == "whatsapp":
            # ссылка wa.me с подставленным приветствием — чистим до base
            base = url.split("?")[0]
            out["whatsapp"].append(base)
        elif t == "telegram":
            out["telegram"].append(url or text)
        elif t == "viber":
            out["viber"].append(url or text)
        elif any(s in t for s in SOCIAL_TYPES) or "instagram" in url.lower() \
                or "facebook" in url.lower() or "tiktok" in url.lower():
            out["social"].append(url or text)
    out["apps"] = rec.get("apps") or []
    out["schedule"] = rec.get("schedule")
    return out


def main():
    rows = json.load(io.open(os.path.join(HERE, "items_all.json"), encoding="utf-8"))
    cards = {}
    path = os.path.join(HERE, "ssr_cards.jsonl")
    if os.path.exists(path):
        for line in io.open(path, encoding="utf-8"):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("ok"):
                cards[rec["id"]] = rec
    agg = OrderedDict()
    summary = Counter()
    for r in rows:
        bucket = "магазины (прочее)"
        for name, test in BUCKETS:
            if test(r):
                bucket = name
                break
        cont = contacts_of(cards.get(r["id"]))
        key_fields = (bucket, r["name"], r["address"], r["district"], r["lat"],
                      r["lon"], r["rating"], r["review_count"],
                      ";".join(r["rubric_names"] or []), r["url_2gis"],
                      "|".join(cont["phones"]), "|".join(cont["website"]),
                      "|".join(cont["whatsapp"]), "|".join(cont["telegram"]),
                      "|".join(cont["viber"]), "|".join(cont["social"]),
                      "|".join(cont["email"]), "|".join(cont["apps"]),
                      cont.get("schedule") or "")
        agg[r["id"]] = key_fields
        summary[bucket] += 1
    with io.open(os.path.join(HERE, "aggregate.tsv"), "w", encoding="utf-8") as fh:
        fh.write("\t".join(("bucket", "name", "address", "district", "lat", "lon",
                            "rating", "reviews", "rubrics", "url_2gis", "phones",
                            "website", "whatsapp", "telegram", "viber", "social",
                            "email", "apps", "hours")) + "\n")
        for fields in agg.values():
            fh.write("\t".join(str(x) if x is not None else "" for x in fields) + "\n")
    enriched = sum(1 for r in rows if r["id"] in cards)
    io.open(os.path.join(HERE, "agg_summary.json"), "w", encoding="utf-8").write(
        json.dumps({"buckets": dict(summary), "rows": len(rows),
                    "with_ssr_contacts": enriched,
                    "with_phone": sum(1 for f in agg.values() if f[10]),
                    "with_website": sum(1 for f in agg.values() if f[11]),
                    "with_whatsapp": sum(1 for f in agg.values() if f[12]),
                    "with_telegram": sum(1 for f in agg.values() if f[13]),
                    "with_social": sum(1 for f in agg.values() if f[15]),
                    "with_apps": sum(1 for f in agg.values() if f[17])},
                   ensure_ascii=False, indent=1))
    print(json.dumps(dict(summary), ensure_ascii=True))


if __name__ == "__main__":
    main()
