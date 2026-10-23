# -*- coding: utf-8 -*-
"""Собрать markdown-блок «Душанбе: каталог жилья» для раздела 2.

usage: python make_md.py

Источник: `housing.jsonl` (2ГИС, Душанбе: выдача + карточки, с рейтингом).

Структура блока:
  1. Проза: сколько объектов снято, сколько с рейтингом >=4.
  2. Топ по рейтингу (4.0+, >=1 отзыв) — одна таблица на всю выборку.
  3. Полный список по типам: Отели/Гостиницы, Гостевые дома/Коттеджи,
     Квартиры посуточно/Апартаменты, Хостелы, Базы отдыха/Пансионаты,
     Прочее жильё. В каждой таблице — Название, Адрес, Рейтинг, Отзывы,
     Телефон, Сайт, WhatsApp, Telegram, Соцсети, Координаты, Карточка.
     Отсекаем объекты с рейтингом <4.0, если рейтинг известен; объекты
     без рейтинга идут в конец блока «без рейтинга».

Все цифры выводятся из самих данных.
"""
import io
import json
import os
import re
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
HOUSING = os.path.join(HERE, "housing.jsonl")
OUT = os.path.join(HERE, "section_2_housing_block.md")

MIN_RATING = 4.0

# BBOX Душанбе и ближайших окрестностей (Гиссар, Вахдат, Туракманшовские
# предгорья). 2ГИС по tadgikiskomu doмену иногда подмешивает карточки из
# московского/российского каталога по тем же рубрикам — режем по координатам.
DUSHANBE_BBOX = (68.30, 38.30, 69.10, 38.95)  # lon_min, lat_min, lon_max, lat_max


def in_dushanbe(rec):
    lon, lat = rec.get("lon"), rec.get("lat")
    if lon is None or lat is None:
        return True  # без координат не режем — решит is_housing/rating
    lo0, la0, lo1, la1 = DUSHANBE_BBOX
    return lo0 <= lon <= lo1 and la0 <= lat <= la1

# Рубрики-подсказки для категоризации.
CATEGORY_RULES = [
    (u"Отели и гостиницы",
     (u"гостиниц", u"отел", u"otel", u"mehmonxona", u"мини-отел")),
    (u"Гостевые дома и коттеджи",
     (u"гостев", u"коттедж", u"аренда коттедж", u"guest house",
      u"дом для приезжих")),
    (u"Квартиры посуточно и апартаменты",
     (u"квартир", u"посуточн", u"апартамент")),
    (u"Хостелы",
     (u"хостел", u"hostel")),
    (u"Базы отдыха, пансионаты, санатории",
     (u"база отдых", u"дом отдых", u"пансионат", u"санатор",
      u"туристическ", u"лагерь")),
]

# Ключевые слова для рубрик/названий, однозначно говорящие о жилье.
HOUSING_KEYS = (
    u"отел", u"гостиниц", u"гостев", u"хостел", u"апарт", u"посуточн",
    u"коттедж", u"пансионат", u"дом отдых", u"база отдых", u"санатор",
    u"mehmonxona", u"mehmon", u"hotel", u"hostel", u"guest house",
    u"otel", u"резиденц",
)

# Шум: то, что 2ГИС может вернуть по запросу "отель/гостиница", но
# жильём не является (турагентства, магазины мебели и пр.).
NON_HOUSING_RUBRICS = (
    u"турагентств", u"туристическ", u"визов", u"авиакасс",
    u"мебел", u"двер", u"окн", u"строймат",
    u"жилищн", u"риэлт", u"агентств недвижимости",
    u"бизнес-центр", u"офис",
    u"кафе", u"ресторан", u"бар", u"банкетн",
    u"свадебн", u"фотостуд",
    u"аптек", u"медицинск", u"стоматол",
    u"магазин", u"супермаркет", u"торгов",
)


def _hit(text, keys):
    text = (text or "").lower()
    return any(k in text for k in keys)


def is_housing(rec):
    rubs = rec.get("rubrics") or []
    # Если хоть одна рубрика выглядит как жильё — берём.
    for r in rubs:
        if _hit(r, HOUSING_KEYS):
            # но не если среди рубрик есть «турагентство»/«мебель»
            if not _hit(r, NON_HOUSING_RUBRICS):
                return True
    text = ((rec.get("name") or "") + " " + (rec.get("card_name") or "") +
            " " + (rec.get("org_name") or ""))
    return _hit(text, HOUSING_KEYS)


def categorize(rec):
    for label, keys in CATEGORY_RULES:
        for r in rec.get("rubrics") or []:
            if _hit(r, keys):
                return label
        if _hit(rec.get("name") or "", keys) or \
           _hit(rec.get("card_name") or "", keys):
            return label
    return u"Прочее жильё"


def fmt_hours(rec):
    if rec.get("card_is_24x7") or rec.get("is_24x7"):
        return u"круглосуточно"
    return rec.get("card_schedule") or u"—"


def first_phone(rec):
    ps = rec.get("phones") or []
    return ps[0] if ps else None


def clean_site(u):
    if not u:
        return None
    if u.startswith("http://") or u.startswith("https://"):
        return u
    return "https://" + u


def first_site(rec):
    ws = rec.get("websites") or []
    return clean_site(ws[0]) if ws else None


WA_RE = re.compile(r"(?:wa\.me|api\.whatsapp\.com/send\?phone=|whatsapp\.com/)",
                   re.IGNORECASE)
TG_RE = re.compile(r"(?:t\.me|telegram\.me|telegram\.im)", re.IGNORECASE)


def _is_wa(v):
    return bool(v) and bool(WA_RE.search(v))


def _is_tg(v):
    return bool(v) and bool(TG_RE.search(v))


def pick_messengers(rec):
    wa = None
    tg = None
    viber = None
    for m in rec.get("messengers") or []:
        u = m if isinstance(m, str) else (m.get("value") or m.get("url") if isinstance(m, dict) else None)
        if not u:
            continue
        if _is_wa(u) and not wa:
            wa = u
        elif _is_tg(u) and not tg:
            tg = u
        elif "viber" in u.lower() and not viber:
            viber = u
    return wa, tg, viber


def pick_socials(rec):
    out = []
    for s in rec.get("socials") or []:
        u = s if isinstance(s, str) else (s.get("value") or s.get("url") if isinstance(s, dict) else None)
        if u:
            out.append(u)
    return out


def escape(s):
    if s is None:
        return ""
    return str(s).replace("|", "\\|").replace("\n", " ")


def load():
    if not os.path.exists(HOUSING):
        return []
    out = []
    for line in io.open(HOUSING, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("is_housing") and is_housing(r) and in_dushanbe(r):
            out.append(r)
    return out


def render_row_cells(r):
    coord = (u"%.6f, %.6f" % (r["lon"], r["lat"])) if r.get("lon") and r.get("lat") else u"—"
    site = first_site(r)
    wa, tg, _viber = pick_messengers(r)
    socs = pick_socials(r)
    rating = r.get("rating")
    rstr = (u"%.1f" % rating) if rating else u"—"
    return {
        "name": escape(r.get("card_name") or r.get("name")),
        "addr": escape(r.get("address_name")),
        "district": escape(r.get("district")),
        "rating": rstr,
        "rev": str(r.get("review_count") or 0),
        "phone": escape(first_phone(r)) or u"—",
        "site": (u"[сайт](%s)" % site) if site else u"—",
        "wa": (u"[WA](%s)" % wa) if wa else u"—",
        "tg": (u"[TG](%s)" % tg) if tg else u"—",
        "socs": (u"[сети](%s)" % socs[0]) if socs else u"—",
        "coord": coord,
        "card": u"[2ГИС](%s)" % escape(r.get("url_2gis")),
    }


def make_table(items, header_only_min=False):
    lines = []
    lines.append(u"| Название | Адрес | Рейтинг | Отзывов | Телефон | "
                 u"Сайт | WhatsApp | Telegram | Соцсети | Координаты | "
                 u"Карточка |")
    lines.append(u"|---|---|---:|---:|---|---|---|---|---|---|---|")
    for r in items:
        c = render_row_cells(r)
        lines.append(u"| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            c["name"], c["addr"], c["rating"], c["rev"], c["phone"],
            c["site"], c["wa"], c["tg"], c["socs"], c["coord"], c["card"]))
    return lines


def main():
    rows = load()
    by_cat = defaultdict(list)
    for r in rows:
        by_cat[categorize(r)].append(r)
    hi = [r for r in rows
          if (r.get("rating") or 0) >= MIN_RATING and (r.get("review_count") or 0) >= 1]
    n_hi = len(hi)
    n_no_rev = sum(1 for r in rows
                   if not r.get("rating") and (r.get("review_count") or 0) == 0)

    lines = []
    lines.append(u"### Душанбе — каталог жилья (2ГИС)")
    lines.append(u"")
    lines.append(u"_Источник: 2ГИС по Душанбе, съём %s. Всего снято %d "
                 u"объектов (отели + гостиницы + гостевые дома + квартиры "
                 u"посуточно + хостелы + прочее жильё), из них %d с рейтингом "
                 u"4.0+ и хотя бы 1 отзывом — эти идут первыми в каждой "
                 u"таблице. Без рейтинга (%d) — в конце раздела, они "
                 u"малоизвестные, но в них тоже можно жить._"
                 % ("2026-10-22", len(rows), n_hi, n_no_rev))
    lines.append(u"")

    cat_order = [c for c, _ in CATEGORY_RULES] + [u"Прочее жильё"]
    for cat in cat_order:
        items = by_cat.get(cat) or []
        if not items:
            continue
        hi_items = sorted(
            [r for r in items
             if (r.get("rating") or 0) >= MIN_RATING and (r.get("review_count") or 0) >= 1],
            key=lambda r: (-(r.get("rating") or 0),
                           -(r.get("review_count") or 0)))
        unranked = [r for r in items if r not in hi_items]
        lines.append(u"#### %s — %d (с рейтингом 4+: %d)" % (
            cat, len(items), len(hi_items)))
        lines.append(u"")
        if hi_items:
            lines.extend(make_table(hi_items))
            lines.append(u"")
        if unranked and cat in (u"Отели и гостиницы",
                                u"Гостевые дома и коттеджи",
                                u"Хостелы",
                                u"Квартиры посуточно и апартаменты"):
            lines.append(u"<details><summary>Без рейтинга / мало отзывов — "
                         u"%d объектов</summary>" % len(unranked))
            lines.append(u"")
            lines.extend(make_table(unranked))
            lines.append(u"")
            lines.append(u"</details>")
            lines.append(u"")
        elif unranked:
            # Короткие категории вроде «Прочего жилья» — без ката: иначе от
            # заголовка с количеством оставалась одна пустая строка.
            lines.extend(make_table(unranked))
            lines.append(u"")

    text = u"\n".join(lines).rstrip() + u"\n"
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(text)
    print("wrote section_2_housing_block.md: %d cats, %d items, %d bytes" % (
        sum(1 for c in cat_order if by_cat.get(c)), len(rows),
        len(text.encode("utf-8"))))


if __name__ == "__main__":
    main()
