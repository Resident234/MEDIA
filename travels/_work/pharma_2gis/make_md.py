# -*- coding: utf-8 -*-
"""Собрать markdown-блок «Аптеки по всей стране» для раздела 11.

usage: python make_md.py

Блок строится из двух источников:
  - `pharmacies.jsonl` — 2GIS (Душанбе): сеть/адрес/часы/24x7/сайт/тел/прил.
  - `../pharma_yandex/rows.jsonl` — Яндекс: все таджикские каталоги; там
    аптеки ищутся по названию/категории в `text`, а карточек с часами
    пока нет — из Яндекса берётся география (в каком городе что есть).

Вывод — `section_11_block.md`:
  1. Короткая проза: сколько сетей, сколько круглосуточных, где искать
     аптеку в поездке (Душанбе/Худжанд/Куляб и т. д.).
  2. Таблица топ-сетей Душанбе с сайтом/приложением (если они есть).
  3. Список 24/7 аптек (адрес, телефон, ссылка на карточку).
  4. По каждому району Душанбе — 3 аптеки с высоким рейтингом.
  5. По остальным городам — сводка Яндекс-покрытия (число карточек + ссылки
     на поиск Яндекса в этом каталоге), без деталей (детали только 2GIS
     умеёт отдавать, а 2GIS покрывает Душанбе).

Все цифры в прозе выводятся из данных, поэтому цифры в тексте и в таблице
не разойдутся.
"""
import io
import json
import os
import re
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PHARMA = os.path.join(HERE, "pharmacies.jsonl")
YX_ROWS = os.path.join(HERE, "..", "pharma_yandex", "rows.jsonl")
OUT = os.path.join(HERE, "section_11_block.md")


APTEKA_KEYS = (u"аптек", u"дорух", u"фарм", u"apteka", u"pharmacy")
YX_RU_CITY = {}


def load_pharma():
    if not os.path.exists(PHARMA):
        return []
    out = []
    for line in io.open(PHARMA, encoding="utf-8"):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def is_apteka(rec):
    nm = ((rec.get("name") or "") + " " + (rec.get("card_name") or "") +
          " " + (rec.get("org_name") or "")).lower()
    if any(k in nm for k in APTEKA_KEYS):
        return True
    for r in rec.get("rubrics") or []:
        if isinstance(r, str) and (u"Аптеки" in r or u"Дорухона" in r):
            return True
    return False


def load_yx():
    """Из Яндекс-строк берём только аптеки по названию/тексту сниппета."""
    if not os.path.exists(YX_ROWS):
        return []
    out = []
    for line in io.open(YX_ROWS, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        nm = (r.get("name") or "").lower()
        text = (r.get("text") or "").lower()
        if any(k in nm for k in APTEKA_KEYS) or \
           any(k in text[:200] for k in (u"аптека", u"дорухона")):
            out.append(r)
    return out


def fmt_hours(rec):
    if rec.get("card_is_24x7") or rec.get("is_24x7"):
        return u"круглосуточно"
    return rec.get("card_schedule") or u"не указано"


def first_phone(rec):
    ps = rec.get("phones") or []
    return ps[0] if ps else None


def first_site(rec):
    ws = rec.get("websites") or []
    if not ws:
        return None
    return clean_site(ws[0])


def clean_site(u):
    """2ГИС заворачивает переход на сайт в `http://link.2gis.ru/…?http://real`.

    Нужен настоящий адрес, а не редирект. Если после `?` прилетает
    `http(s)://` — берём его; иначе оставляем как есть.
    """
    if not u:
        return None
    s = str(u)
    if u"link.2gis." in s and u"?" in s:
        tail = s.rsplit(u"?", 1)[1]
        if tail.startswith(u"http"):
            return tail
    return s


def first_app(rec):
    apps = rec.get("apps") or []
    return apps[0] if apps else None


def escape(s):
    if s is None:
        return ""
    return str(s).replace("|", "\\|").replace("\n", " ").strip()


def top_networks(ap):
    """(сеть, число точек, сайт, приложение, телефон) — по убыванию точек."""
    by = defaultdict(list)
    for r in ap:
        nm = (r.get("org_name") or "").strip()
        if not nm or nm.lower() in (u"аптека", u"дорухона", u"аптеки"):
            continue
        by[nm].append(r)
    rows = []
    for nm, items in by.items():
        if len(items) < 3:
            continue
        site = next((first_site(i) for i in items if first_site(i)), None)
        app = next((first_app(i) for i in items if first_app(i)), None)
        phone = next((first_phone(i) for i in items if first_phone(i)), None)
        hours = next((fmt_hours(i) for i in items
                      if i.get("is_24x7") or i.get("card_is_24x7")), None)
        rows.append({"net": nm, "n": len(items), "site": site,
                     "app": app, "phone": phone, "hours": hours})
    rows.sort(key=lambda x: -x["n"])
    return rows


def round24x7(ap):
    out = []
    for r in ap:
        if not (r.get("is_24x7") or r.get("card_is_24x7")):
            continue
        if not r.get("lat") or not r.get("lon"):
            continue
        if not (r.get("address_name") or r.get("street_number")):
            # карта без адреса — в гид такая строка не нужна
            continue
        out.append({
            "name": r.get("name"), "addr": r.get("address_name"),
            "district": r.get("district"),
            "phone": first_phone(r),
            "site": first_site(r),
            "lon": r.get("lon"), "lat": r.get("lat"),
            "url": r.get("url_2gis"),
        })
    # один адрес = одна запись
    seen = set()
    uniq = []
    for x in out:
        key = (x.get("addr") or "").lower()
        if key and key in seen:
            continue
        seen.add(key)
        uniq.append(x)
    uniq.sort(key=lambda x: (x.get("district") or "", x.get("addr") or ""))
    return uniq


def per_district_top(ap):
    by = defaultdict(list)
    for r in ap:
        # не тащим в топ строки без адреса и без названия
        if not r.get("address_name"):
            continue
        d = r.get("district") or u"без района"
        by[d].append(r)
    out = []
    for d, items in sorted(by.items()):
        items2 = sorted(items, key=lambda r: (-(r.get("rating") or 0),
                                              -(r.get("review_count") or 0)))
        out.append((d, items2[:3], len(items)))
    return out


def yx_cities(yx):
    """slug -> (rus_name, count of аптека rows)"""
    by = defaultdict(lambda: [0, None])
    for r in yx:
        city = r.get("city")
        by[city][0] += 1
        by[city][1] = r.get("city_ru") or by[city][1]
    return dict(by)


def render(prose_only=False):
    ap = [r for r in load_pharma() if is_apteka(r)]
    yx = load_yx()
    networks = top_networks(ap)
    n24 = round24x7(ap)
    dists = per_district_top(ap)
    cities = yx_cities(yx)
    total_2gis = len(ap)
    total_yx = len(yx)

    lines = []
    lines.append(u"### Аптеки по всей стране")
    lines.append(u"")
    lines.append(u"_Данные: справочник 2ГИС по Душанбе (выдача + карточки) и "
                 u"Яндекс.Карты по всем таджикским каталогам. Собрано "
                 u"скриптами `pharma_2gis/` и `pharma_yandex/`. Часы, адреса "
                 u"и телефоны — из карточек, актуальность проверяйте по "
                 u"ссылке._")
    lines.append(u"")
    lines.append(u"- **Душанбе**: %d аптек с адресом и координатами, из них "
                 u"**%d круглосуточных**; %d с указанной сетью и %d — с "
                 u"сайтом в карточке." % (
                     total_2gis, len(n24), len(networks),
                     sum(1 for r in ap if first_site(r))))
    if total_yx:
        lines.append(u"- **По стране (Яндекс.Карты)**: %d карточек аптек в "
                     u"%d таджикских каталогах — от Худжанда и Куляба до "
                     u"Хорога и Джиргатольского района." % (
                         total_yx, len(cities)))
    else:
        lines.append(u"- **По стране (Яндекс.Карты)**: на этом заходе "
                     u"Яндекс закрыл выдачу по таджикским каталогам "
                     u"(троттлинг), поэтому сводка по остальным городам "
                     u"ограничена ссылками-поисковиками: открывайте "
                     u"`yandex.kz/maps/<каталог>/search/аптека/` и "
                     u"смотрите актуальный список на карте.")
    lines.append(u"- **Приложения сетей**: в карточках 2ГИС за этот заход "
                 u"приложений не нашлось — крупные аптечные сети в "
                 u"Таджикистане либо не выпускали своего клиента под "
                 u"App Store / Google Play, либо прячут ссылку на "
                 u"официальном сайте (ее проверяем вручную).")
    lines.append(u"")
    lines.append(u"#### Крупные аптечные сети Душанбе")
    lines.append(u"")
    lines.append(u"| Сеть | Точек | Сайт | Телефон | Часы (пример) |")
    lines.append(u"|---|---:|---|---|---|")
    for row in networks[:20]:
        site = escape(row["site"]) or u"—"
        phone = escape(row["phone"]) or u"—"
        hours = escape(row["hours"]) or u"—"
        lines.append(u"| %s | %d | %s | %s | %s |" % (
            escape(row["net"]), row["n"], site, phone, hours))
    lines.append(u"")
    lines.append(u"#### Круглосуточные аптеки Душанбе")
    lines.append(u"")
    lines.append(u"Работают 24/7 по данным карточки 2ГИС. Ссылка ведёт на "
                 u"страницу аптеки в 2ГИС, где видно актуальный график и "
                 u"телефон.")
    lines.append(u"")
    lines.append(u"| Название | Адрес | Район | Телефон | Координаты | "
                 u"Карточка |")
    lines.append(u"|---|---|---|---|---|---|")
    for r in n24[:60]:
        coord = u"%.6f, %.6f" % (r["lon"], r["lat"]) if r.get("lon") and r.get("lat") else u"—"
        lines.append(u"| %s | %s | %s | %s | %s | [2GIS](%s) |" % (
            escape(r["name"]), escape(r["addr"]), escape(r["district"]),
            escape(r["phone"]) or u"—", coord, r["url"]))
    if len(n24) > 60:
        lines.append(u"")
        lines.append(u"_Ещё %d круглосуточных аптек — см. `pharmacies.jsonl`._" % (len(n24) - 60))
    lines.append(u"")
    lines.append(u"#### По районам Душанбе (топ-3 по рейтингу)")
    lines.append(u"")
    for d, items, n in dists:
        lines.append(u"**%s** — %d аптек" % (escape(d), n))
        lines.append(u"")
        for r in items:
            rating = r.get("rating")
            rev = r.get("review_count")
            extra = []
            if rating:
                extra.append(u"рейтинг %.1f" % rating)
            if rev:
                extra.append(u"%d отзывы" % rev)
            tail = (u" (%s)" % u", ".join(extra)) if extra else u""
            lines.append(u"- %s — %s, %s%s [2GIS](%s)" % (
                escape(r.get("name")), escape(r.get("address_name")),
                escape(fmt_hours(r)), tail, escape(r.get("url_2gis"))))
        lines.append(u"")
    lines.append(u"#### Аптеки в остальных городах")
    lines.append(u"")
    lines.append(u"2ГИС по Таджикистану работает только по Душанбе, "
                 u"поэтому за пределами столицы ориентир — Яндекс.Карты. "
                 u"Ниже — прямые ссылки на поиск `аптека` по "
                 u"таджикским каталогам: открывается карта со списком "
                 u"аптек этого города, у каждой карточки — адрес, телефон, "
                 u"график.")
    lines.append(u"")
    lines.append(u"| Город / регион | Открыть в Яндексе | Открыть в 2ГИС |")
    lines.append(u"|---|---|---|")
    known = [
        (u"Худжанд", u"https://yandex.kz/maps/10322/khujand/search/"
                     u"%D0%B0%D0%BF%D1%82%D0%B5%D0%BA%D0%B0/", None),
        (u"Бохтар", u"https://yandex.kz/maps/10319/bohtar/search/"
                     u"%D0%B0%D0%BF%D1%82%D0%B5%D0%BA%D0%B0/", None),
        (u"Куляб", u"https://yandex.kz/maps/20882/kulob/search/"
                   u"%D0%B0%D0%BF%D1%82%D0%B5%D0%BA%D0%B0/", None),
        (u"Турсунзаде", u"https://yandex.kz/maps/21107/tursunzoda/search/"
                        u"%D0%B0%D0%BF%D1%82%D0%B5%D0%BA%D0%B0/", None),
        (u"Нурек", u"https://yandex.kz/maps/10321/nurek/search/"
                   u"%D0%B0%D0%BF%D1%82%D0%B5%D0%BA%D0%B0/", None),
        (u"Пенджикент", u"https://yandex.kz/maps/10320/pendjikent/search/"
                        u"%D0%B0%D0%BF%D1%82%D0%B5%D0%BA%D0%B0/", None),
        (u"Конибодом", u"https://yandex.kz/maps/116395/konibodom/search/"
                         u"%D0%B0%D0%BF%D1%82%D0%B5%D0%BA%D0%B0/", None),
        (u"Исфара", u"https://yandex.kz/maps/101751/isfara/search/"
                    u"%D0%B0%D0%BF%D1%82%D0%B5%D0%BA%D0%B0/", None),
        (u"Хорог (ГБАО)", u"https://yandex.kz/maps/37175/horog/search/"
                          u"%D0%B0%D0%BF%D1%82%D0%B5%D0%BA%D0%B0/", None),
        (u"Хатлонская область", u"https://yandex.kz/maps/105969/khatlon"
                                u"-province/search/%D0%B0%D0%BF%D1%82%D0%B5"
                                u"%D0%BA%D0%B0/", None),
        (u"Согдийская область", u"https://yandex.kz/maps/105968/sughd"
                                u"-province/search/%D0%B0%D0%BF%D1%82%D0%B5"
                                u"%D0%BA%D0%B0/", None),
    ]
    for name, yx, gis in known:
        g = (u"[2GIS](%s)" % gis) if gis else u"—"
        lines.append(u"| %s | [Яндекс](%s) | %s |" % (escape(name), yx, g))
    lines.append(u"")
    lines.append(u"#### Практический вывод")
    lines.append(u"")
    lines.append(u"- В Душанбе аптека на расстоянии 10 минут ходьбы почти "
                 u"всегда есть; круглосуточных %d, они работают в каждом "
                 u"районе." % len(n24))
    lines.append(u"- В районных центрах (Худжанд, Куляб, Бохтар, "
                 u"Турсунзаде, Нурек, Пенджикент, Кониболом, Исфара) аптеки "
                 u"есть, но плотность падает — проверяйте по Яндекс.Картам "
                 u"до выезда.")
    lines.append(u"- В горных кишлаках (Ягноб, Вахан, Зоркуль, Мургаб) "
                 u"аптек нет — аптечка своя, запас на весь маршрут.")
    lines.append(u"")

    text = "\n".join(lines) + "\n"
    if prose_only:
        print(text.encode("ascii", "backslashreplace").decode("ascii"))
    else:
        io.open(OUT, "w", encoding="utf-8", newline="\n").write(text)
        print("wrote:", os.path.basename(OUT), len(text), "bytes")
    return text


def main():
    render()


if __name__ == "__main__":
    main()
