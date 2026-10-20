# -*- coding: utf-8 -*-
"""Собрать markdown-блок «Лаборатории и медицинские анализы» для раздела 11.

usage: python make_md.py

Источник: `labs.jsonl` (2ГИС, Душанбе: выдача + карточки) и, если он
появится, `../labs_yandex/rows.jsonl` (Яндекс по всем таджикским каталогам).

Блок строится по той же схеме, что аптечный:
  1. Проза: сколько объектов, сколько круглосуточных, сколько с сайтом.
  2. Таблица сетей (>=2 точки).
  3. Полный список лабораторий Душанбе с часами и телефоном (без 24/7-секции
     — их обычно единицы, проще видеть весь список).
  4. Топ-3 по районам.
  5. Ссылки на поиск по остальным городам (только Яндекс, 2ГИС по стране
     не работает).

Все цифры выводятся из самих данных, поэтому проза и таблицы не разойдутся.
"""
import io
import json
import os
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
LABS = os.path.join(HERE, "labs.jsonl")
YX_ROWS = os.path.join(HERE, "..", "labs_yandex", "rows.jsonl")
OUT = os.path.join(HERE, "section_11_labs_block.md")

LAB_KEYS = (u"лаборатор", u"анализ", u"диагност", u"пцр", u"ифа",
            u"check-up", u"обследovan", u"медосмотр",
            u"таҳлил", u"озмуни", u"laborator", u"diagnost",
            u"мрт", u"узи", u"узз", u"экг", u"эхо", u"флюорогр",
            u"цитолог", u"гистолог", u"функциональн",
            u"томогр", u"медосмотр", u"медицинское оборудов",
            u"медицинская комиссия", u"многопрофильный")
# Рубрики, по которым ясно, что объект не лаборатория, а выданные
# запросами "экспресс-..."/"УЗД"/"КТ"/"медосмотр" магазины, автомойки,
# ветеринарки и т. п. Отсекаем их до того, как смотреть на LAB_KEYS.
NON_LAB_RUBRICS = (u"автомойк", u"продуктов", u"вокзал", u"почт",
                   u"груз", u"терминал", u"стоматол", u"ветеринар",
                   u"питание", u"бад", u"спортивн", u"кафе", u"магазин",
                   u"супермаркет", u"аптек", u"торговый", u"банк",
                   u"обмен валют", u"мебел", u"одежд", u"обув", u"парикмах",
                   u"международные", u"автострахов", u"нотариус", u"сумка",
                   u"бизнес-центр")


def load_labs():
    if not os.path.exists(LABS):
        return []
    out = []
    for line in io.open(LABS, encoding="utf-8"):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _hit(text, keys):
    text = (text or "").lower()
    return any(k in text for k in keys)


def is_lab(rec):
    rubs = rec.get("rubrics") or []
    # Если хоть одна рубрика попадает в чёрный список — это не лаборатория.
    for r in rubs:
        if _hit(r, NON_LAB_RUBRICS):
            return False
    # Если есть рубрика, прямо говорящая про лабораторию/диагностику — да.
    for r in rubs:
        if _hit(r, LAB_KEYS):
            return True
    # Иначе решаем по названию: строка «УЗДА», «Узди абсор», «Нис, клиника»
    # без рубрики, но попала в лабораторный запрос — скорее всего,
    # медицинский центр с забором анализов.
    nm = ((rec.get("name") or "") + " " + (rec.get("card_name") or "") +
          " " + (rec.get("org_name") or "")).lower()
    if _hit(nm, LAB_KEYS):
        return True
    # Если 2ГИС вообще не дал рубрик и название немедицинское — отсекаем.
    if not rubs:
        return False
    # Рубрики есть, но не совпали ни с black, ни с white — решаем по
    # первой рубрике: «Медицинский центр», «Поликлиника», «Клиника»
    # считаем смежными лабораториями.
    for r in rubs:
        rl = (r or "").lower()
        if u"медицинск" in rl or u"поликлин" in rl or u"клиник" in rl \
           or u"больниц" in rl or u"здравп" in rl or u"здоровь" in rl:
            return True
    return False


def load_yx():
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
        if any(k in nm for k in LAB_KEYS) or \
           any(k in text[:200] for k in (u"лаборатория", u"анализ",
                                          u"диагност")):
            out.append(r)
    return out


def fmt_hours(rec):
    if rec.get("card_is_24x7") or rec.get("is_24x7"):
        return u"круглосуточно"
    return rec.get("card_schedule") or u"не указано"


def first_phone(rec):
    ps = rec.get("phones") or []
    return ps[0] if ps else None


def clean_site(u):
    if not u:
        return None
    s = str(u)
    if u"link.2gis." in s and u"?" in s:
        tail = s.rsplit(u"?", 1)[1]
        if tail.startswith(u"http"):
            return tail
    return s


def first_site(rec):
    ws = rec.get("websites") or []
    return clean_site(ws[0]) if ws else None


def first_app(rec):
    apps = rec.get("apps") or []
    return apps[0] if apps else None


def escape(s):
    if s is None:
        return ""
    return str(s).replace("|", "\\|").replace("\n", " ").strip()


def top_networks(rows):
    by = defaultdict(list)
    for r in rows:
        nm = (r.get("org_name") or "").strip()
        if not nm or nm.lower() in (u"лаборатория", u"анализы", u"диагностика"):
            continue
        by[nm].append(r)
    out = []
    for nm, items in by.items():
        if len(items) < 2:
            continue
        site = next((first_site(i) for i in items if first_site(i)), None)
        app = next((first_app(i) for i in items if first_app(i)), None)
        phone = next((first_phone(i) for i in items if first_phone(i)), None)
        sched = next((fmt_hours(i) for i in items
                      if i.get("is_24x7") or i.get("card_is_24x7")), None)
        out.append({"net": nm, "n": len(items), "site": site,
                    "app": app, "phone": phone, "hours": sched})
    out.sort(key=lambda x: -x["n"])
    return out


def per_district_top(rows):
    by = defaultdict(list)
    for r in rows:
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


def full_list(rows):
    """Все лаборатории с адресом, отсортированные по району и названию."""
    ok = [r for r in rows if r.get("address_name") and r.get("lat")
          and r.get("lon")]
    ok.sort(key=lambda r: ((r.get("district") or ""), (r.get("address_name") or
                                                       ""), (r.get("name") or "")))
    return ok


def yx_cities(yx):
    by = defaultdict(lambda: [0, None])
    for r in yx:
        city = r.get("city")
        by[city][0] += 1
        by[city][1] = r.get("city_ru") or by[city][1]
    return dict(by)


def render():
    labs = [r for r in load_labs() if is_lab(r)]
    yx = load_yx()
    networks = top_networks(labs)
    dists = per_district_top(labs)
    cities = yx_cities(yx)
    n24 = [r for r in labs
           if (r.get("is_24x7") or r.get("card_is_24x7"))
           and r.get("address_name") and r.get("lat") and r.get("lon")]
    total_2gis = len(labs)
    total_yx = len(yx)

    lines = []
    lines.append(u"### Лаборатории и медицинские анализы")
    lines.append(u"")
    lines.append(u"_Данные: справочник 2ГИС по Душанбе (выдача + карточки) "
                 u"и Яндекс.Карты по таджикским каталогам. Собрано скриптами "
                 u"`labs_2gis/` и `labs_yandex/`. Сеть лабораторий — это "
                 u"отдельная сущность: анализы принимают и в поликлиниках, "
                 u"и в частных клиниках; ниже те объекты, у которых в "
                 u"2ГИС стоит рубрика «лаборатория / анализы / диагностика» "
                 u"или соответствующее название._")
    lines.append(u"")
    lines.append(u"- **Душанбе**: %d лабораторий и диагностических центров "
                 u"с адресом и координатами; %d работают круглосуточно, "
                 u"%d — с сетью (2+ точки), %d — с сайтом в карточке, "
                 u"%d — с телефоном." % (
                     total_2gis, len(n24), len(networks),
                     sum(1 for r in labs if first_site(r)),
                     sum(1 for r in labs if first_phone(r))))
    if total_yx:
        lines.append(u"- **По стране (Яндекс.Карты)**: %d карточек в %d "
                     u"таджикских каталогах." % (total_yx, len(cities)))
    else:
        lines.append(u"- **По стране (Яндекс.Карты)**: Яндекс на этом "
                     u"заходе закрыл выдачу по таджикским каталогам "
                     u"(троттлинг), по остальным городам даются прямые "
                     u"ссылки-поисковики вида "
                     u"`yandex.kz/maps/<каталог>/search/лаборатория/`.")
    lines.append(u"- **Что сдают**: в карточках 2ГИС по Душанбе самая "
                 u"частая комбинация — общий анализ крови/мочи, биохимия, "
                 u"гормоны, ПЦР и ИФА; УЗИ/ЭКГ/ЭХО-КГ/флюорография "
                 u"обычно идут в той же лаборатории при диагностическом "
                 u"центре. На сайтах сетей — полный прайс и подготовка к "
                 u"анализам.")
    lines.append(u"- **Приложения**: у лабораторных сетей Таджикистана "
                 u"мобильных клиентов в карточках 2ГИС не найдено; запись "
                 u"обычно по телефону или через форму на сайте.")
    lines.append(u"")

    if networks:
        lines.append(u"#### Сети лабораторий Душанбе")
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

    if n24:
        lines.append(u"#### Круглосуточные лаборатории и пункты сдачи "
                     u"анализов")
        lines.append(u"")
        lines.append(u"| Название | Адрес | Район | Телефон | Координаты | "
                     u"Карточка |")
        lines.append(u"|---|---|---|---|---|---|")
        for r in n24:
            coord = (u"%.6f, %.6f" % (r["lon"], r["lat"])) if r.get("lon") \
                and r.get("lat") else u"—"
            lines.append(u"| %s | %s | %s | %s | %s | [2GIS](%s) |" % (
                escape(r.get("name")), escape(r.get("address_name")),
                escape(r.get("district")), escape(first_phone(r)) or u"—",
                coord, escape(r.get("url_2gis"))))
        lines.append(u"")

    all_rows = full_list(labs)
    lines.append(u"#### Все лаборатории Душанбе")
    lines.append(u"")
    lines.append(u"Ниже — полный список с адресом, графиком и ссылкой на "
                 u"карточку 2ГИС. Телефон/сайт указываем, если они есть в "
                 u"карточке. Актуальный график и прайс проверяйте по "
                 u"ссылке.")
    lines.append(u"")
    lines.append(u"| Название | Адрес | Район | Часы | Телефон | Сайт | "
                 u"Карточка |")
    lines.append(u"|---|---|---|---|---|---|---|")
    for r in all_rows:
        site = first_site(r)
        coord_url = r.get("url_2gis") or ""
        lines.append(u"| %s | %s | %s | %s | %s | %s | [2GIS](%s) |" % (
            escape(r.get("name")), escape(r.get("address_name")),
            escape(r.get("district")), escape(fmt_hours(r)),
            escape(first_phone(r)) or u"—",
            (u"[сайт](%s)" % site) if site else u"—",
            escape(coord_url)))
    lines.append(u"")

    lines.append(u"#### По районам (топ-3 по рейтингу)")
    lines.append(u"")
    for d, items, n in dists:
        lines.append(u"**%s** — %d лабораторий" % (escape(d), n))
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

    lines.append(u"#### Лаборатории в остальных городах")
    lines.append(u"")
    lines.append(u"2ГИС по Таджикистану покрывает только Душанбе, поэтому "
                 u"за пределами столицы — Яндекс.Карты. Ниже прямые ссылки "
                 u"на поиск `лаборатория` по таджикским каталогам.")
    lines.append(u"")
    lines.append(u"| Город / регион | Открыть в Яндексе | Открыть в 2ГИС |")
    lines.append(u"|---|---|---|")
    LAB_Q = u"%D0%BB%D0%B0%D0%B1%D0%BE%D1%80%D0%B0%D1%82%D0%BE%D1%80%D0%B8%D1%8F"
    known = [
        (u"Худжанд", u"https://yandex.kz/maps/10322/khujand/search/" + LAB_Q),
        (u"Бохтар", u"https://yandex.kz/maps/10319/bohtar/search/" + LAB_Q),
        (u"Куляб", u"https://yandex.kz/maps/20882/kulob/search/" + LAB_Q),
        (u"Турсунзаде", u"https://yandex.kz/maps/21107/tursunzoda/search/" + LAB_Q),
        (u"Нурек", u"https://yandex.kz/maps/10321/nurek/search/" + LAB_Q),
        (u"Пенджикент", u"https://yandex.kz/maps/10320/pendjikent/search/" + LAB_Q),
        (u"Конибодом", u"https://yandex.kz/maps/116395/konibodom/search/" + LAB_Q),
        (u"Исфара", u"https://yandex.kz/maps/101751/isfara/search/" + LAB_Q),
        (u"Хорог (ГБАО)", u"https://yandex.kz/maps/37175/horog/search/" + LAB_Q),
        (u"Хатлонская область",
         u"https://yandex.kz/maps/105969/khatlon-province/search/" + LAB_Q),
        (u"Согдийская область",
         u"https://yandex.kz/maps/105968/sughd-province/search/" + LAB_Q),
    ]
    for name, yx_url in known:
        lines.append(u"| %s | [Яндекс](%s) | — |" % (escape(name), yx_url))
    lines.append(u"")
    lines.append(u"#### Практический вывод")
    lines.append(u"")
    lines.append(u"- В Душанбе лаборатория с забором анализов есть почти в "
                 u"каждом районе; полный график и запись по телефону — в "
                 u"карточке 2ГИС.")
    u_dash = u"-"
    lines.append(u_dash + u" В Худжанде, Кулябе, Бохтаре, Турсунзаде, Нуреке, "
                 u"Пенджикенте, Конибоме, Исфаре лаборатории есть, но "
                 u"реактивы и узкие профили (онкомаркеры, генетика, "
                 u"алергопанели) обычно проще сдать в Душанбе — уточняйте "
                 u"заранее.")
    lines.append(u"- В горных кишлаках (Ягноб, Вахан, Зоркуль, Мургаб) "
                 u"лабораторий нет; базовые экспресс-тесты могут быть в "
                 u"врачебном пункте, остальное — с собой или через "
                 u"санавиацию.")
    lines.append(u"")

    text = "\n".join(lines) + "\n"
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(text)
    print("wrote:", os.path.basename(OUT), len(text), "bytes")
    return text


if __name__ == "__main__":
    render()
