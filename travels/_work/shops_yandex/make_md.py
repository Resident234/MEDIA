# -*- coding: utf-8 -*-
"""Assemble the map-data subsections for build/70_pokupki.md.

usage: python make_md.py   -> section_8_map_data.md (+ appendix_2gis_full.tsv)

Reads the finished ledgers of both passes and renders markdown in the style
85_fitness.md established (one bullet per card: name; address; coordinates;
card link; then phones/site/messengers/social/apps — only what the card
actually gave). Nothing is invented: a field that the source does not have is
omitted from the line, and coverage stats are printed so the prose can quote
them. Inputs are read fresh on every run, so the script can be re-run as the
crawls complete. Missing inputs are skipped with a note, not an error.

Sources:
  shops_2gis/items_all.json       collected cards (API)      [done]
  shops_2gis/ssr_cards.jsonl      web-card contacts          [crawl]
  shops_2gis/rows.jsonl           named-places API pass      [done]
  shops_yandex/rows.jsonl         named+category list pass   [run]
  shops_yandex/all.tsv             parsed yandex cards        [after parse_rows]
  shops_yandex/cards/*.json       opened yandex cards         [after yx_shopcards]
"""
import glob
import io
import json
import os
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "section_8_map_data.md")
APPX = os.path.join(HERE, "appendix_2gis_full.tsv")
BUILD = os.path.join(HERE, "..", "build", "70_pokupki.md")
BEGIN = "<!-- BEGIN generated: shops_yandex/make_md.py -->"
END = "<!-- END generated -->"

CAT_WORDS = {"базар", "рынок", "торговый центр", "супермаркет", "гипермаркет",
             "магазин", "дукон", "интернет-магазин", "маркетплейс",
             "пункт выдачи", "ремесла", "сувениры"}
KEY_BUCKETS = ["базары и рынки", "ярмарки", "торговые центры", "гипермаркеты",
               "супермаркеты", "пункты выдачи (ПВЗ)",
               "интернет-магазины и маркетплейсы", "ремёсла и сувениры"]
SOCIAL_TYPES = ("instagram", "facebook", "tiktok", "youtube", "ok", "twitter",
                "vk", "odnoklassniki", "pinterest", "linkedin")


def jload(path):
    if not os.path.exists(path):
        return None
    return json.load(io.open(path, encoding="utf-8"))


def jlines(path):
    if not os.path.exists(path):
        return []
    out = []
    for line in io.open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def addr_text(item):
    a = item.get("address")
    if isinstance(a, dict):
        parts = [c.get("type") for c in a.get("components") or []]
        comp = a.get("components") or []
        loc = next((c.get("comment") for c in comp if c.get("type") == "location"), "")
        street = next((c.get("history_name") or c.get("name") for c in comp
                       if c.get("type") in ("street", "address")), "")
        num = next((c.get("name") for c in comp if c.get("type") == "address"), "")
        s = ", ".join(x for x in (loc, street, num) if x)
        return s or json.dumps(a, ensure_ascii=False)
    return a or ""


def clean_link(link):
    """HTML entities / escaping artefacts off an app-store or redirect URL."""
    import html as _html
    s = _html.unescape(link or "")
    return s.replace("\\/", "/").rstrip("\\").strip()


def site_domain(rec):
    """Host of the website contact (the human text, not the 2GIS redirect)."""
    import re as _re
    from urllib.parse import urlparse
    for c in (rec or {}).get("contacts") or []:
        if (c.get("type") or "").lower() != "website":
            continue
        text = (c.get("text") or "").strip()
        url = (c.get("url") or c.get("value") or "")
        m = _re.search(r"\?(https?://.+)$", url)
        host = urlparse((m.group(1) if m else "http://" + text)).netloc.lower()
        host = _re.sub(r"^www\.", "", host)
        if host and "2gis" not in host:
            return host
    return None


def contacts_from_ssr(rec):
    """Same mapping aggregate.py uses, kept as ordered label:value pairs."""
    out = OrderedDict()
    if not rec:
        return out
    phones, site, wa, tg, viber, social, email, apps = \
        [], [], [], [], [], [], [], []
    for c in rec.get("contacts") or []:
        t = (c.get("type") or "").lower()
        text = (c.get("text") or "").strip()
        url = (c.get("url") or c.get("value") or "").strip()
        if t == "phone":
            phones.append(text or url)
        elif t == "website":
            site.append(text or url)
        elif t == "email":
            email.append(text or url)
        elif t == "whatsapp":
            wa.append(url.split("?")[0])
        elif t == "telegram":
            tg.append(url or text)
        elif t == "viber":
            viber.append(url or text)
        elif any(s in t for s in SOCIAL_TYPES) or any(
                s in url.lower() for s in ("instagram", "facebook", "tiktok")):
            social.append(url or text)
    apps = rec.get("apps") or []
    for label, vals in (("телефон", phones), ("сайт", site), ("WhatsApp", wa),
                        ("Telegram", tg), ("Viber", viber), ("соцсети", social),
                        ("почта", email), ("приложения", apps)):
        if vals:
            out[label] = vals
    if rec.get("schedule"):
        out["часы"] = [rec["schedule"]]
    return out


def contact_md(cons):
    return "; ".join("%s: %s" % (k, ", ".join(v)) for k, v in cons.items())


def cons_of(gssr, appsite, item_id):
    """SSR contacts, plus app links found on that card's own website."""
    rec = gssr.get(item_id)
    cons = contacts_from_ssr(rec)
    if rec is not None:
        host = site_domain(rec)
        got = [clean_link(a) for a in ((appsite.get(host) or {}).get("own") or [])] \
            if host else []
        if got and "приложения" not in cons:
            cons["приложения с сайта"] = got
    return cons


def card_line(item, cons):
    bits = ["**%s**" % item["name"]]
    a = addr_text(item)
    if a:
        bits.append(a)
    if item.get("district"):
        bits.append("район %s" % item["district"])
    if item.get("rating") is not None:
        r = ("%s" % item["rating"]).replace(".", ",")
        bits.append("рейтинг %s%s" % (r, ", отзывов %s" % item["review_count"]
                                     if item.get("review_count") else ""))
    if item.get("rubric_names"):
        bits.append("рубрика: " + ", ".join(item["rubric_names"]))
    if item.get("lat") is not None and item.get("lon") is not None:
        bits.append("координаты (широта, долгота) %.6f, %.6f" %
                    (item["lat"], item["lon"]))
    else:
        bits.append("координат в карточке нет")
    c = contact_md(cons)
    if c:
        bits.append(c)
    bits.append("карточка: %s" % item["url_2gis"])
    return "- " + "; ".join(bits) + ".\n"


def yx_name_pairs(rows_yx):
    """Group yandex rows.jsonl by (city, query) for the name pass only."""
    got = OrderedDict()
    for r in rows_yx:
        if r.get("query") in CAT_WORDS:
            continue
        got.setdefault((r["city"], r["query"]), []).append(r)
    return got


def lookup_outcomes(path):
    """Parse lookup.log lines 'HH:MM:SS city query kind n=X' into counters."""
    if not os.path.exists(path):
        return None
    kinds = {}
    cities = set()
    pairs = set()
    for line in io.open(path, encoding="utf-8"):
        c = line.split()
        if len(c) < 4:
            continue
        if c[-1] == "NOCATALOG":
            kinds["nocatalog"] = kinds.get("nocatalog", 0) + 1
            cities.add(c[1])
            pairs.add((c[1], " ".join(c[2:-1])))
            continue
        city, kind = c[1], c[-2] if c[-1].startswith("n=") else c[-1]
        if not c[-1].startswith("n="):
            continue
        kinds[kind] = kinds.get(kind, 0) + 1
        cities.add(city)
        pairs.add((city, " ".join(c[2:-2])))
    return {"kinds": kinds, "cities": len(cities), "pairs": len(pairs),
            "rows": len(jlines(os.path.join(HERE, "rows.jsonl")))}


def snippet_fields(text):
    """Rating/address/category words out of a Yandex snippet or card body."""
    import re
    t = text or ""
    out = {}
    m = re.search(r"Рейтинг\s*\|\s*(\d+)[,.](\d+)(?:\s*\|\s*(\d+)\s*(?:оценок|оценки|отзывов|оценка))?", t)
    if m:
        out["rating"] = "%s,%s" % (m.group(1), m.group(2))
        out["votes"] = m.group(3)
    else:
        m = re.search(r"Оценка (\d+[.,]\d+)", t)
        if m:
            out["rating"] = m.group(1)
    for p in [x.strip() for x in t.split("|")]:
        if re.search(r"(ул\.|просп|наб\.|переулок|мкр|район|б-р|шоссе|кв\.|улица|кӯча)", p):
            out["addr"] = p
            break
    return out


def yx_bits(r, card=None):
    href = r.get("href") or r.get("url") or ""
    url = href if href.startswith("http") else ("https://yandex.kz" + href)
    bits = ["- **%s**" % (r.get("name") or "?")]
    p = snippet_fields(r.get("text") or "")
    if r.get("addr"):
        bits.append(str(r["addr"]))
    elif p.get("addr"):
        bits.append(p["addr"])
    rating = r.get("rating") or p.get("rating")
    if rating:
        votes = r.get("reviews") or p.get("votes")
        bits.append("рейтинг %s%s" % (rating, ", оценок %s" % votes if votes else ""))
    if r.get("cats"):
        bits.append("рубрика: %s" % r["cats"])
    coords = r.get("coords")
    if coords:
        lon, lat = (str(coords).split(",") + ["", ""])[:2]
        bits.append("координаты (широта, долгота) %s, %s" % (lat.strip(), lon.strip()))
    if card:
        cc = yx_card_contacts(card)
        if cc:
            bits.append(cc)
    if url:
        bits.append("карточка: %s" % url)
    return bits


def read_all_tsv(path):
    """all.tsv (parse_rows.py) -> {city: [rows with id/coords filled in]}."""
    if not os.path.exists(path):
        return None
    out = OrderedDict()
    with io.open(path, encoding="utf-8") as fh:
        head = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            c = line.rstrip("\n").split("\t")
            if len(c) < len(head):
                c += [""] * (len(head) - len(c))
            r = dict(zip(head, c))
            url = r.get("url") or ""
            r["id"] = url.rstrip("/").split("/")[-1] if url else ""
            if r.get("lon") and r.get("lat"):
                r["coords"] = "%s,%s" % (r["lon"], r["lat"])
            out.setdefault(r["city"], []).append(r)
    return out or None


CITY_ORDER = ["dushanbe", "khujand", "bohtar", "kulob", "tursunzoda",
              "pendjikent", "horog", "nurek", "isfara", "konibodom",
              "sughd-province", "khatlon-province",
              "gorno-badakhshan-autonomous-province", "hisor-district",
              "rudaki-district"]
RU = {"dushanbe": "Душанбе", "khujand": "Худжанд", "bohtar": "Бохтар",
      "kulob": "Куляб", "tursunzoda": "Турсунзаде", "pendjikent": "Пенджикент",
      "horog": "Хорог", "nurek": "Нурек", "isfara": "Исфара",
      "konibodom": "Канибадам", "sughd-province": "Согд. область",
      "khatlon-province": "Хатлон. область",
      "gorno-badakhshan-autonomous-province": "ГБАО",
      "hisor-district": "район Гиссар", "rudaki-district": "район Рудаки"}


def order_cities(yall):
    known = [c for c in CITY_ORDER if c in yall]
    return known + sorted(c for c in yall if c not in known)


def city_ru(city, rs):
    ru = RU.get(city)
    return "%s (`%s`)" % (ru, city) if ru else city


def cov_row(label, items, gcons):
    """Строка таблицы покрытия: сколько в bucket'е карточек и что у них заполнено."""
    rated = [i for i in items if i.get("rating") is not None]
    row = [label, len(items), len(rated),
           sum(1 for i in rated if (i["rating"] or 0) >= 4.0)]
    for k in ("телефон", "сайт", "WhatsApp", "Telegram", "соцсети", "часы"):
        row.append(sum(1 for i in items if k in (gcons.get(i["id"]) or {})))
    return "| " + " | ".join(str(x) for x in row) + " |\n"


def main():
    gitems = jload(os.path.join(HERE, "..", "shops_2gis", "items_all.json")) or []
    gssr = {r["id"]: r for r in jlines(os.path.join(HERE, "..", "shops_2gis",
                                                    "ssr_cards.jsonl")) if r.get("ok")}
    appsite = jload(os.path.join(HERE, "apps_sites.json")) or {}
    gnames = [r for r in jlines(os.path.join(HERE, "..", "shops_2gis", "rows.jsonl"))
              if r.get("kind") == "name"]
    yrows = jlines(os.path.join(HERE, "rows.jsonl"))
    yall = read_all_tsv(os.path.join(HERE, "all.tsv")) or {}
    ycards = {}
    for p in glob.glob(os.path.join(HERE, "cards", "*.json")):
        try:
            ycards[os.path.basename(p)[:-5]] = json.load(io.open(p, encoding="utf-8"))
        except ValueError:
            pass

    # раскладка по bucket'ам нужна и сводке покрытия, и списку ниже — считаем её
    # один раз здесь.
    buckets = OrderedDict((b, []) for b in KEY_BUCKETS)
    tail_items = []
    for it in gitems:
        b = bucket_of(it)
        if b is None:
            tail_items.append(it)
        else:
            buckets[b].append(it)
    tail = len(tail_items)
    gcons = {it["id"]: cons_of(gssr, appsite, it["id"]) for it in gitems}

    fh = io.open(OUT, "w", encoding="utf-8", newline="\n")
    fh.write("<!-- generated by shops_yandex/make_md.py; правки поверх -->\n\n")

    # ---------- 0) collection evidence ----------
    coll = jload(os.path.join(HERE, "..", "shops_2gis", "collect_report.json"))
    agg = jload(os.path.join(HERE, "..", "shops_2gis", "agg_summary.json"))
    nocov = jload(os.path.join(HERE, "_no_cover.json"))
    outcomes = lookup_outcomes(os.path.join(HERE, "lookup.log"))
    if coll or agg or outcomes or gssr:
        fh.write("### Как собрана эта часть и что она покрывает (сводка сборщика)\n\n")
        if coll:
            fh.write("**2ГИС, раскладка по запросам** (объявленный total против "
                     "собранного по плиткам; `trunc` — плитки, упиравшиеся в "
                     "потолок демо-ключа):\n\n")
            fh.write("| путь | объявлено (city_id) | сумма total по плиткам | плиток "
                     "без результата | trunc | unique карточек с этим путём |\n"
                     "|---|---|---|---|---|---|\n")
            for p in coll.get("passes") or []:
                tiles = p.get("tiles") or []
                trunc = sum(1 for t in tiles if t.get("truncated"))
                nulls = sum(1 for t in tiles if not t.get("total"))
                tsum = sum(t.get("total") or 0 for t in tiles)
                lbl = p.get("pass")
                n_have = sum(1 for it in gitems if lbl in (it.get("passes") or []))
                fh.write("| %s | %s | %d | %d | %d | %d |\n" % (
                    json.dumps(lbl, ensure_ascii=False),
                    "—" if p.get("declared_total") is None else p.get("declared_total"),
                    tsum, nulls, trunc, n_have))
            fh.write("\nвсего уникальных карточек %d, обращений к API %d.\n\n" %
                     (coll.get("total_items"), coll.get("requests_made")))
            notes = []
            for p in coll.get("passes") or []:
                t = sum(1 for x in (p.get("tiles") or []) if x.get("truncated"))
                if t:
                    notes.append("%s — %d плиток" % (
                        json.dumps(p.get("pass"), ensure_ascii=False), t))
            if notes:
                fh.write("Потолок демо-ключа (5 карточек × 10 на запрос) не снят "
                         "даже плитками: упирались в него " + "; ".join(notes) +
                         ". Плитки делят город до 7-го уровня — это примерно "
                         "0,3×0,3 км; значит, по этим словам в Душанбе больше "
                         "карточек, чем отдал ключ, и собранный список по ним "
                         "неполон. Запрошенные категории (базар, рынок, ТЦ, "
                         "супермаркет, ПВЗ, ремесла, сувениры) в потолок не "
                         "упирались — по ним массив полный.\n\n")
            fh.write("Колонка «объявлено» — это `total` того же запроса без "
                     "пространственного ограничения (по `city_id`), она не обязана "
                     "совпадать с суммой по плиткам: у «торговый центр» плитки "
                     "дали больше (одна карточка попадает в несколько плиток на "
                     "границах), у «рынок» и «интернет-магазин» — меньше. Рабочая цифра — "
                     "сумма собранных unique-карточек, а не любой из тоталов."
                     " У рубричных путей объявленный тотал отсутствует: пробный "
                     "запрос на него ничего не вернул (повторить 20.10.2026 не "
                     "удалось — к этому часу демо-ключ был заблокирован самим "
                     "2ГИС, `403 apiKeyIsBlocked`); польза рубричных прогонов "
                     "поэтому не в тотале, а в карточках, которых не дали "
                     "текстовые запросы — они в последней колонке.\n\n")
            cid = {}
            for it in gitems:
                for pl in it.get("passes") or []:
                    if pl.startswith("cityid:"):
                        cid[pl] = cid.get(pl, 0) + 1
            if cid:
                fh.write("Тем же прогоном каждый запрос был запрошен и без плиток — "
                         "через `city_id` (этот путь не ограничивает выдачу строго, "
                         "поэтому он служит только сверкой тоталов); карточек с этим "
                         "путём: %s.\n\n" % ", ".join(
                             "%s — %d" % (json.dumps(k[7:], ensure_ascii=False), v)
                             for k, v in sorted(cid.items(), key=lambda kv: -kv[1])))
        if gssr:
            cs = [gcons[i["id"]] for i in gitems]
            fh.write("**2ГИС, контакты со страниц карточек:** %d карточек из %d "
                     "обойдено; телефон у %d, сайт у %d, WhatsApp у %d, "
                     "Telegram у %d, соцсети у %d, часы у %d, приложения у %d.\n\n" % (
                         len(gssr), len(gitems),
                         sum(1 for c in cs if "телефон" in c),
                         sum(1 for c in cs if "сайт" in c),
                         sum(1 for c in cs if "WhatsApp" in c),
                         sum(1 for c in cs if "Telegram" in c),
                         sum(1 for c in cs if "соцсети" in c),
                         sum(1 for c in cs if "часы" in c),
                         sum(1 for c in cs if "приложения" in c or
                             "приложения с сайта" in c)))
            fh.write("| bucket | карточек | с рейтингом | он же ≥ 4,0 | с телефоном | "
                     "с сайтом | с WhatsApp | с Telegram | с соцсетями | с часами |\n"
                     "|---|---|---|---|---|---|---|---|---|---|\n")
            for b in KEY_BUCKETS:
                fh.write(cov_row(b, buckets[b], gcons))
            fh.write(cov_row("магазины (прочее)", tail_items, gcons))
            fh.write(cov_row("ИТОГО", gitems, gcons))
            fh.write("\n")
            if appsite:
                hits = {k: v for k, v in appsite.items() if v.get("own")}
                fh.write("Ни одна обойдённая страница карточки 2ГИС не отдаёт ссылок "
                         "на приложения, поэтому они сняты с сайтов самих "
                         "организаций: проверено %d доменов, ссылки на магазины "
                         "приложений найдены у %d — %s. В список они попадают только "
                         "у той карточки, чей сайт их содержит.\n\n" % (
                             len(appsite), len(hits), ", ".join(
                                 json.dumps(k, ensure_ascii=False) for k in sorted(hits))))
        if nocov is not None:
            nc = nocov if isinstance(nocov, list) else sorted(nocov.keys())
            fh.write("**Яндекс, города без собственного каталога** (проверено, "
                     "карточка города не найдена — их район/область снимается "
                     "через провинциальный каталог): %s.\n\n" %
                     ", ".join(json.dumps(x, ensure_ascii=False) for x in nc))
        if outcomes:
            fh.write("**Яндекс, итоги по парам «каталог|запрос»** (list — список "
                     "выдачи, org — поиск открыл единственную карточку, empty — «ничего "
                     "не нашлось», none/timeout — страница не отдала результата):\n\n")
            fh.write("| исход | пар |\n|---|---|\n")
            for k, v in sorted(outcomes["kinds"].items()):
                fh.write("| %s | %d |\n" % (k, v))
            fh.write("\nпар в работе/готово: %d, каталогов: %d, карточек в "
                     "буфере: %d.\n\n" % (outcomes["pairs"], outcomes["cities"],
                                          outcomes["rows"]))

    # ---------- 1) named places: 2GIS side ----------
    fh.write("### Данные карт: названные места (2ГИС)\n\n")
    by_q = OrderedDict()
    for r in gnames:
        by_q.setdefault(r["query"], []).append(r)
    for q, rs in by_q.items():
        fh.write("**%s**\n\n" % q)
        for r in rs[:3]:
            cons = gcons.get(r["id"]) or cons_of(gssr, appsite, r["id"])
            bits = ["- **%s**" % r["name"]]
            if r.get("address"):
                bits.append(str(r["address"]))
            if r.get("district"):
                bits.append("район %s" % r["district"])
            if r.get("rating") is not None:
                bits.append("рейтинг %s%s" % (
                    ("%s" % r["rating"]).replace(".", ","),
                    ", отзывов %s" % r["reviews"] if r.get("reviews") else ""))
            if r.get("lat") is not None and r.get("lon") is not None:
                bits.append("координаты (широта, долгота) %.6f, %.6f" %
                            (r["lat"], r["lon"]))
            c = contact_md(cons)
            if c:
                bits.append(c)
            bits.append("карточка: %s" % r["url"])
            fh.write("; ".join(bits) + ".\n")
        if len(rs) > 3:
            fh.write("- (ещё %d карточек по этому запросу — в массиве)\n" % (len(rs) - 3))
        fh.write("\n")

    # ---------- 2) named places: Yandex side ----------
    fh.write("### Данные карт: названные места (Яндекс.Карты)\n\n")
    pairs = yx_name_pairs(yrows)
    named_cities = 0
    for city in order_cities(yall):
        rs = [r for r in yall[city] if r.get("named") == "True"]
        if not rs:
            continue
        named_cities += len(rs)
        fh.write("**%s** — %d карточек, найденных по названиям из раздела\n\n" %
                 (city_ru(city, rs), len(rs)))
        rs.sort(key=lambda x: (x.get("name") or ""))
        for r in rs:
            cid = r.get("id") or (r.get("url") or "").rstrip("/").split("/")[-1]
            bits = yx_bits(r, ycards.get(cid))
            bits.insert(1, "найдено поиском: %s" % (r.get("src") or "?"))
            fh.write("; ".join(bits) + ".\n")
        fh.write("\n")
    if not named_cities:
        # all.tsv ещё нет, но пары уже отработаны — показываем сырые строки;
        # дедупликации тут нет, это только промежуточный вид списка.
        for (city, q), rs in pairs.items():
            fh.write("**%s** — поиск «%s» в каталоге %s\n\n" % (q, city, city))
            for r in rs[:3]:
                href = r.get("href") or ""
                cid = r.get("id") or href.rstrip("/").split("/")[-1]
                fh.write("; ".join(yx_bits(r, ycards.get(cid))) + ".\n")
            if len(rs) > 3:
                fh.write("- (ещё %d результатов по этому запросу — в массиве)\n" % (len(rs) - 3))
            fh.write("\n")
        if not pairs:
            fh.write("`[ещё не собрано — yx_lookup идёт]`\n\n")
    else:
        fh.write("Карточка стоит в этом списке один раз на город; после слова "
                 "«найдено поиском» перечислены все запросы, которыми она "
                 "отдалась (сырые строки `rows.jsonl` повторяют её на каждом "
                 "запросе).\n\n")

    # ---------- 3) 2GIS category buckets ----------
    fh.write("### Данные карт: категории по Душанбе (2ГИС)\n\n")
    fh.write("Карточка отнесена в первый совпавший bucket (специфичные стоят "
             "выше родового); поэтому число в bucket — не число найденных по слову "
             "карточек: часть найденных по «ярмарка» или «базар» уже стоит в "
             "более раннем bucket, а точные числа по путям — в таблице сбора выше.\n\n")
    for b in KEY_BUCKETS:
        items = buckets[b]
        fh.write("#### %s — %d карточек\n\n" % (b, len(items)))
        items.sort(key=lambda x: (-(x.get("rating") or 0), x["name"]))
        for it in items:
            fh.write(card_line(it, gcons[it["id"]]))
        fh.write("\n")
    fh.write("#### Магазины прочие — %d карточек\n\nполный список со всеми "
             "контактами — в `_work/shops_yandex/appendix_2gis_full.tsv` (колонки "
             "от bucket до apps, генерируется вместе с этим текстом) и в "
             "`_work/shops_2gis/aggregate.tsv` (то же без приложений с сайтов); "
             "в справочник построчно не внесён, потому это родовая корзина, а не "
             "запрошенная категория.\n\n" % tail)

    # ---------- 4) Yandex per-city ----------
    fh.write("### Данные карт: категории по городам страны (Яндекс.Карты)\n\n")
    if yall:
        fh.write("Список дедуплицирован по карточкам (одна организация один раз на "
                 "город, отдельной строкой — каким поиском найдена). В карточке "
                 "`all.tsv` рейтинг и адрес прочитаны из сниппета; контакты и "
                 "ссылки — только у открытых карточек (`cards/`).\n\n")
        gen = {"магазин", "дукон"}
        for city in order_cities(yall):
            rs = yall[city]
            key = [r for r in rs if set((r.get("src") or "").split("+")) - gen]
            nrest = len(rs) - len(key)
            fh.write("#### %s — %d карточек (по ключевым категориям %d, по родовым "
                     "«магазин»/«дукон» ещё %d)\n\n" % (
                         city_ru(city, rs), len(rs), len(key), nrest))
            key.sort(key=lambda x: (-(float(x.get("rating") or 0)), x.get("name") or ""))
            for r in key:
                cid = r.get("id") or (r.get("url") or "").rstrip("/").split("/")[-1]
                bits = yx_bits(r, ycards.get(cid))
                bits.insert(1, "найдено поиском: %s" % (r.get("src") or "?"))
                fh.write("; ".join(bits) + ".\n")
            fh.write("\n")
    elif yrows:
        cat = [r for r in yrows if r.get("query") in CAT_WORDS]
        bycity = OrderedDict()
        for r in cat:
            bycity.setdefault(r["city"], []).append(r)
        for city, rs in bycity.items():
            uniq = {}
            for r in rs:
                uniq.setdefault(r.get("id") or r.get("href"), r)
            fh.write("#### %s — %d уникальных карточек\n\n" % (city, len(uniq)))
            for r in sorted(uniq.values(), key=lambda x: (x.get("query") or "",
                                                           x.get("name") or "")):
                href = r.get("href") or ""
                if "/maps/org/" not in href:
                    continue
                bits = ["- **%s** (поиск «%s»)" % (r.get("name") or "?", r.get("query"))]
                bits += yx_bits(r)[1:]
                fh.write("; ".join(bits) + ".\n")
            fh.write("\n")
    else:
        fh.write("`[ещё не собрано]`\n\n")
    fh.close()

    # ---------- appendix ----------
    with io.open(APPX, "w", encoding="utf-8", newline="\n") as af:
        af.write("bucket\tname\taddress\tdistrict\tlat\tlon\trating\treviews\t"
                 "rubrics\turl_2gis\tphones\twebsite\twhatsapp\ttelegram\tsocial\thours\tapps\n")
        for it in gitems:
            cons = gcons[it["id"]]
            row = [bucket_of(it) or "магазины (прочее)", it["name"], addr_text(it),
                   it.get("district") or "",
                   "" if it.get("lat") is None else "%.6f" % it["lat"],
                   "" if it.get("lon") is None else "%.6f" % it["lon"],
                   "" if it.get("rating") is None else it["rating"],
                   it.get("review_count") or "", ";".join(it.get("rubric_names") or []),
                   it["url_2gis"]]
            for label in ("телефон", "сайт", "WhatsApp", "Telegram", "соцсети", "часы"):
                row.append(",".join(cons.get(label) or []))
            row.append(",".join((cons.get("приложения") or []) +
                                (cons.get("приложения с сайта") or [])))
            af.write("\t".join(str(x) for x in row) + "\n")

    n_2gis = len(gitems)
    print(json.dumps({"2gis_items": n_2gis, "2gis_ssr_done": len(gssr),
                      "2gis_name_queries": len(by_q),
                      "yx_rows": len(yrows), "yx_name_pairs": len(pairs),
                      "yx_cards_opened": len(ycards),
                      "buckets": {b: len(v) for b, v in buckets.items()},
                      "tail": tail,
                      "build": splice_into_build()}, ensure_ascii=True))


def splice_into_build():
    """Перегнать сгенерированный блок в build/70_pokupki.md между маркерами.

    Проза раздела пишется руками, список карточек — нет; чтобы правки данных
    не требовали ручной вставки, make_md заменяет только то, что лежит между
    BEGIN и END. Вне маркеров его запись не трогает.
    """
    if not os.path.exists(BUILD):
        return "нет build/70_pokupki.md"
    text = io.open(BUILD, encoding="utf-8").read()
    if BEGIN not in text or END not in text:
        return "маркеры не найдены — блок не вставлен"
    body = io.open(OUT, encoding="utf-8").read().split("\n")
    body = "\n".join(body[1:]).strip("\n")     # первая строка — служебный комментарий
    head, rest = text.split(BEGIN, 1)
    tail = rest.split(END, 1)[1]
    new = head + BEGIN + "\n\n" + body + "\n\n" + END + tail
    if new != text:
        with io.open(BUILD, "w", encoding="utf-8", newline="\n") as bf:
            bf.write(new)
    return "вставлено %d строк" % len(body.split("\n"))


def bucket_of(it):
    passes = set(it.get("passes") or [])
    rub = set(it.get("rubric_ids") or [])
    names = " ".join((n or "").lower() for n in it.get("rubric_names") or [])
    # «интернет-магазин» в 2ГИС ищет по словам, и в выдачу попадают интернет-
    # провайдеры (Babilon-T, Sa-net, Tojiktelecom). В онлайн-категорию их не
    # берём: родовая корзина честнее, чем чужая строка в запрошенной категории.
    provider = ("провайдер" in names or "provider" in names
                or "интернет хизматрасонӣ" in names)
    if passes & {"query:базар", "query:бозор", "query:рынок"} or "бозор" in names or "рынок" in names:
        return "базары и рынки"
    if "query:ярмарка" in passes:
        return "ярмарки"
    if "query:торговый центр" in passes or "торговый центр" in names or "савдо маркази" in names:
        return "торговые центры"
    if "12127" in rub or "query:гипермаркет" in passes:
        return "гипермаркеты"
    if "350" in rub or "query:супермаркет" in passes:
        return "супермаркеты"
    if "112611" in rub or "query:пункт выдачи" in passes:
        return "пункты выдачи (ПВЗ)"
    if passes & {"query:интернет-магазин", "query:маркетплейс"} and not provider:
        return "интернет-магазины и маркетплейсы"
    if rub & {"110333", "510"} or passes & {"query:ремесла", "query:сувениры"}:
        return "ремёсла и сувениры"
    return None


def yx_card_contacts(card):
    """Render one contacts line from a cards/<id>.json dump (yx_card2.js)."""
    YX = ("mapsyandex", "yandex.maps", "zen.yandex")
    bits = []
    phones = [p.get("t") for p in card.get("phones") or [] if p.get("t")]
    if phones:
        bits.append("телефон: " + ", ".join(phones[:3]))
    for l in card.get("extLinks") or []:
        h = l.get("h") or ""
        if h and not any(y in h for y in YX) and "yandex" not in h:
            bits.append("сайт: " + h)
            break
    wa = [l["h"] for l in card.get("msgLinks") or []
          if l.get("ownOrg") and ("wa.me" in l["h"] or "whatsapp" in l["h"])]
    if wa:
        bits.append("WhatsApp: " + ", ".join(wa[:2]))
    tg = [l["h"] for l in card.get("msgLinks") or []
          if l.get("ownOrg") and ("t.me" in l["h"] or "telegram" in l["h"])]
    if tg:
        bits.append("Telegram: " + ", ".join(tg[:2]))
    soc = [l["h"] for l in card.get("social") or []
           if l.get("h") and not any(y in l["h"] for y in YX)]
    if soc:
        bits.append("соцсети: " + ", ".join(soc[:3]))
    apps = [l["h"] for l in card.get("apps") or [] if l.get("h")]
    if apps:
        bits.append("приложения: " + ", ".join(apps[:3]))
    return "; ".join(bits)


if __name__ == "__main__":
    main()
