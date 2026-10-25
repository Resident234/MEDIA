# -*- coding: utf-8 -*-
"""Собрать md-блок «Жильё по стране — Яндекс Карты» и вставить его в раздел 2.

usage:
  python mkblock.py            # собрать section_yx_block.md и вставить в 20_zhile.md
  python mkblock.py --no-splice

Читает housing_yx.jsonl (см. merge.py), группирует объекты по региону, внутри
региона — по городам. Объекты с рейтингом идут первыми таблицей, остальные
(малоизвестные, но живые) — под катом, как в блоке 2ГИС.

Маркеры в build/20_zhile.md: HOUSING_YX_BLOCK_BEGIN / HOUSING_YX_BLOCK_END.
Первый раз блок вставляется перед подзаголовком «### Ночёвки в дороге», то
есть сразу после блока 2ГИС.
"""
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "housing_yx.jsonl")
OUT = os.path.join(HERE, "section_yx_block.md")
DST = os.path.join(HERE, "..", "build", "20_zhile.md")
BEGIN = u"<!-- HOUSING_YX_BLOCK_BEGIN -->"
END = u"<!-- HOUSING_YX_BLOCK_END -->"
ANCHOR = u"\n### Ноч\u0451вки в дороге"

REGION_ORDER = [u"Душанбе", u"РРП", u"Хатлон", u"Согд", u"ГБАО", u"прочее"]
HEAD = (u"| Название | Город | Адрес | Рейтинг | Отзывов | Телефоны | Сайт | "
        u"Соцсети | Координаты | Карточка |\n"
        u"|---|---|---|---:|---:|---|---|---|---|---|")
SOC_LABEL = {"whatsapp": "WA", "telegram": "TG", "instagram": "IG",
             "facebook": "FB", "vk": "VK", "ok": "OK", "youtube": "YT",
             "twitter": "X", "viber": "Viber"}


def esc(text):
    return (text or u"").replace(u"|", u"/").replace(u"\n", u" ").strip()


def host(url):
    m = re.match(r"https?://([^/]+)", url or "")
    h = m.group(1) if m else url
    return h.replace("www.", "")


def soc_label(url, kind):
    if kind == "whatsapp" or "wa.me" in url:
        return "WA"
    if kind == "telegram" or "t.me" in url:
        return "TG"
    if "instagram" in url:
        return "IG"
    if "facebook" in url:
        return "FB"
    if "vk.com" in url:
        return "VK"
    if "ok.ru" in url:
        return "OK"
    if "youtube" in url:
        return "YT"
    return SOC_LABEL.get(kind, "сети")


def row(r):
    phones = "<br>".join(esc(p) for p in r.get("phones", [])[:4]) or u"—"
    site = u"—"
    if r.get("sites"):
        u0 = r["sites"][0]
        site = u"[%s](%s)" % (esc(host(u0)), u0)
    links, used = [], set()
    for u0 in r.get("whatsapp", [])[:1]:
        links.append(u"[WA](%s)" % u0)
        used.add("WA")
    for u0 in r.get("telegram", [])[:1]:
        links.append(u"[TG](%s)" % u0)
        used.add("TG")
    for u0 in r.get("socials", []):
        lab = soc_label(u0, "")
        if lab in used:
            continue
        used.add(lab)
        links.append(u"[%s](%s)" % (lab, u0))
        if len(used) >= 4:
            break
    socials = u" ".join(links) or u"—"
    coords = u"—"
    if r.get("lon") is not None:
        coords = u"%.4f, %.4f" % (r["lon"], r["lat"])
    rating = u"%.1f" % r["rating"] if r.get("rating") else u"—"
    rev = str(r["reviews"]) if r.get("reviews") else u"—"
    card = u"[Яндекс](%s)" % r["url"] if r.get("url") else u"—"
    return u"| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
        esc(r.get("name")), esc(r.get("city")), esc(r.get("address")),
        rating, rev, phones, site, socials, coords, card)


def block(rows):
    rated = [r for r in rows if r.get("rating")]
    plain = [r for r in rows if not r.get("rating")]
    rated.sort(key=lambda r: (-(r["rating"] or 0), -(r["reviews"] or 0),
                              r["name"]))
    plain.sort(key=lambda r: (r.get("city") or "", r["name"]))
    out = []
    if rated:
        out.append(HEAD)
        out.extend(row(r) for r in rated)
        out.append(u"")
    if plain:
        out.append(u"<details><summary>Без рейтинга — %d объектов</summary>"
                   % len(plain))
        out.append(u"")
        out.append(HEAD)
        out.extend(row(r) for r in plain)
        out.append(u"")
        out.append(u"</details>")
        out.append(u"")
    return u"\n".join(out)


def main():
    rows = [json.loads(line) for line in io.open(SRC, encoding="utf-8")
            if line.strip()]
    if not rows:
        raise SystemExit("no rows in housing_yx.jsonl")
    towns = sorted({r["city"] for r in rows if r.get("city")})
    rated = sum(1 for r in rows if r.get("rating"))
    phones = sum(1 for r in rows if r.get("phones"))
    sites = sum(1 for r in rows if r.get("sites"))
    socials = sum(1 for r in rows if r.get("socials")
                  or r.get("whatsapp") or r.get("telegram"))
    by_region = {}
    for r in rows:
        by_region.setdefault(r.get("region") or u"прочее", []).append(r)

    parts = [u"### Жильё по стране — Яндекс Карты", u""]
    parts.append(
        u"_Источник: Яндекс Карты, съём %s. Объектов: **%d**, населённых "
        u"пунктов: **%d** — гостиницы, гостевые дома, квартиры посуточно, "
        u"хостелы, мотели, базы отдыха и кемпинги. Телефоны есть у %d, "
        u"сайт — у %d, соцсети или "
        u"WhatsApp/Telegram — у %d, рейтинг с отзывами — у %d (эти идут первыми, "
        u"остальные под катом: живые, но малоизвестные)._"
        % (time.strftime("%Y-%m-%d"), len(rows), len(towns), phones, sites,
           socials, rated))

    top = sorted(by_region.items(),
                 key=lambda kv: REGION_ORDER.index(kv[0])
                 if kv[0] in REGION_ORDER else 99)
    for region, items in top:
        items.sort(key=lambda r: (r.get("city") or "", -(r["rating"] or 0),
                                  -(r["reviews"] or 0), r.get("name") or ""))
        cnt = {}
        for r in items:
            cnt[r.get("city")] = cnt.get(r.get("city"), 0) + 1
        towns_line = u", ".join(u"%s — %d" % (c, n) for c, n in
                                sorted(cnt.items(), key=lambda kv: (-kv[1],
                                                                    kv[0])))
        parts.append(u"")
        parts.append(u"#### %s — %d" % (region, len(items)))
        parts.append(u"")
        if len(cnt) > 1:
            parts.append(u"_%s._" % towns_line)
            parts.append(u"")
        parts.append(block(items))

    text = u"\n".join(parts).strip() + u"\n"
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(text)
    print("block: %d rows, %d towns -> %s" % (
        len(rows), len(towns), os.path.basename(OUT)))

    if "--no-splice" in sys.argv:
        return
    body = io.open(DST, encoding="utf-8").read()
    wrapped = BEGIN + u"\n\n" + text.strip() + u"\n\n" + END
    b, e = body.find(BEGIN), body.find(END)
    if b >= 0 and e > b:
        new, action = body[:b] + wrapped + body[e + len(END):], "replaced"
    else:
        pos = body.find(ANCHOR)
        if pos < 0:
            raise SystemExit("anchor not found: " +
                             ANCHOR.encode("unicode_escape").decode("ascii"))
        new, action = body[:pos] + u"\n" + wrapped + body[pos:], "inserted"
    io.open(DST, "w", encoding="utf-8", newline="\n").write(new)
    print("%s, %d bytes -> build/20_zhile.md" % (action, len(wrapped)))


if __name__ == "__main__":
    main()
