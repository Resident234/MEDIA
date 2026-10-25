# -*- coding: utf-8 -*-
"""Собрать markdown-блок «Еда: заведения Душанбе и других городов» для раздела 7.

usage: python make_md.py

Источник:
  - `food.jsonl` (2ГИС, Душанбе: выдача + карточки, с рейтингом);
  - `../food_yandex/rows.jsonl` (Яндекс по таджикским каталогам) — если
    прогон прошёл, иначе ссылки-поисковики.

Структура:
  1. Проза: сколько объектов, сколько с рейтингом >=4, разбивка по типам.
  2. Сети (>=3 точки), с сайтами и приложениями.
  3. Топ-25 заведений по рейтингу (>=4, отзывов >=5) — «куда пойти».
  4. Полный список по типам (Чайханы / Рестораны / Кафе / Бары/Паб/Караоке /
     Кофейни/Пекарни / Фудкорты/Столовые / Доставка еды) с адресом, часами,
     телефоном, сайтом, соцсетями, координатами, ссылкой на карточку.
     Отсекаем объекты с рейтингом <4.0, если рейтинг известен; объекты без
     рейтинга (малоизвестные) идут в конец блока «без рейтинга».
  5. По районам — топ-3.
  6. Карточки Яндекса по городам из `../food_yandex/cards_block.md` (если
     прогон там уже прошёл) — Душанбе и остальные города; иначе — ссылки на
     поиск по каталогам.

Все цифры выводятся из самих данных.
"""
import io
import json
import os
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
FOOD = os.path.join(HERE, "food.jsonl")
YX_ROWS = os.path.join(HERE, "..", "food_yandex", "rows.jsonl")
YX_BLOCK = os.path.join(HERE, "..", "food_yandex", "cards_block.md")
OUT = os.path.join(HERE, "section_7_food_block.md")

MIN_RATING = 4.0

# Рубрики, по которым объект не является заведением общепита (шум от
# запросов "бар" -> "бар на воде", "кафе" -> "кондитерский цех при магазине",
# "доставка" -> курьерские службы). Отсекаются до whitelist.
NON_FOOD_RUBRICS = (
    u"_supermarket", u"супермаркет", u"магазин продуктов",
    u"продуктовый", u"гипермаркет", u"рынок",
    u"база отдыха", u"гостиниц", u"отель", u"мотель",
    u"хостел", u"пансионат", u"санаторий",
    u"детский центр", u"игровая", u"развлечений",
    u"банкетный зал", u"конференц",
    u"свадебный", u"ритуальн",
    u"аптек", u"медицинск", u"стоматол", u"ветеринар",
    u"автомойк", u"автосервис", u"шиномонтаж", u"АЗС",
    u"АЗС", u"заправк",
    u"груз", u"перевозк", u"курьер",
    u"химчистк", u"прачечн",
    u"бан", u"обмен валют", u"ломбард",
    u"одежд", u"обув", u"мебел", u"книжн", u"строймат",
    u"свадьб", u"фотостуд",
    u"аренда",
)

# Ключевые слова для рубрик/названий, однозначно говорящие о заведении.
FOOD_KEYS = (
    u"кафе", u"бар", u"ресторан", u"чайхана", u"чойхона", u"кофейн",
    u"паб", u"фудкорт", u"фуд-корт", u"фуд корт", u"пицц", u"суши",
    u"ролл", u"шаурм", u"шаурма", u"лагман", u"шашлы", u"мангал",
    u"кальян", u"пекарн", u"булочн", u"кондитер", u"столов",
    u"быстрое питание", u"фастфуд", u"бургер", u"хинкальн",
    u"закусочн", u"караок", u"дискотек", u"ночной клуб", u"рестобар",
    u"гастробар", u"суши-бар", u"питейн", u"пивн", u"винн", u"кофейня",
    u"oshxona", u"oshxona", u"кафе-бар", u"кафе-кондитерск",
    u"доставка готов", u"доставка еды", u"доставка блюд",
    u"ресторан быстрого питания", u"кофейный автомат",
)

# Категории для группировки списка. Порядок — как в выводе.
CATEGORY_RULES = [
    (u"Чайханы", (u"чайхана", u"чойхона", u"oshxona", u"осуйхона",
                  u"максум", u"нахлебаев", u"чойхона")),
    (u"Рестораны", (u"ресторан", u"рестобар", u"гастробар", u"restaurant",
                    u"кафе-ресторан", u"ресторан-бар")),
    (u"Кафе", (u"кафе", u"закусочная", u"кафешка", u"кафе-бар",
               u"кондитерская", u"пекарня-кафе", u"пекарн", u"булочн",
               u"пиццерия", u"пицц", u"суши", u"ролл", u"шаурм", u"шаурма",
               u"лагман", u"шашлычн", u"мангал", u"бургерн", u"фастфуд",
               u"быстрое питание", u"плов", u"хинкальн", u"пирожк",
               u"пончик", u"кофейня-кондитерск", u"кафе-пекарн",
               u"dhaba", u"ресторан быстрого питания", u"столовая",
               u"столов")),
    (u"Бары, пабы, караоке и клубы", (u"бар", u"паб", u"пивн", u"питейн",
                                       u"кальян", u"караок", u"дискотек",
                                       u"ночной клуб", u"клуб",
                                       u"винос", u"винный",
                                       u"суши-бар", u"кофейн")),
    (u"Кофейни и кондитерские", (u"кофейн", u"кофе", u"кондитер",
                                  u"пекарн", u"булочн", u"тест", u"десерт",
                                  u"караул", u"кофе-пойнт", u"кофе-точка",
                                  u"кофе-автомат", u"айс", u"морожен")),
    (u"Фудкорты и фуд-холлы", (u"фудкорт", u"фуд-корт", u"фуд корт",
                                u"food court", u"фудхолл", u"фуд-холл",
                                u"food hall", u"фудмолл", u"фуд-молл")),
    (u"Доставка еды", (u"доставка", u"delivery", u"сеты", u"на дом",
                       u"доставка еды", u"доставка готов")),
]


def load_food():
    if not os.path.exists(FOOD):
        return []
    out = []
    for line in io.open(FOOD, encoding="utf-8"):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _hit(text, keys):
    text = (text or "").lower()
    return any(k in text for k in keys)


def is_food(rec):
    rubs = rec.get("rubrics") or []
    for r in rubs:
        if _hit(r, NON_FOOD_RUBRICS):
            return False
    for r in rubs:
        if _hit(r, FOOD_KEYS):
            return True
    nm = ((rec.get("name") or "") + " " + (rec.get("card_name") or "") +
          " " + (rec.get("org_name") or "")).lower()
    return _hit(nm, FOOD_KEYS)


def categorize(rec):
    """Определяет подкатегорию для отображения полного списка."""
    text = ((rec.get("name") or "") + " " + (rec.get("card_name") or "") +
            " " + " ".join(rec.get("rubrics") or [])).lower()
    for cat, keys in CATEGORY_RULES:
        if _hit(text, keys):
            return cat
    return u"Прочие заведения"


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


def socials(rec):
    out = []
    for s in rec.get("socials") or []:
        out.append(s if isinstance(s, str) else str(s))
    for m in rec.get("messengers") or []:
        if isinstance(m, str) and m.startswith("http"):
            out.append(m)
    return out


def escape(s):
    if s is None:
        return ""
    return str(s).replace("|", "\\|").replace("\n", " ").strip()


def top_networks(rows):
    # 2GIS часто ставит в org_name родовое слово («Бистро», «Бар», «Кафе»).
    # Считаем сетью только те org_name, где есть хоть одно имя собственное.
    GENERIC_NET = (
        u"бистро", u"быстро", u"быстрое питание", u"фастфуд", u"бар",
        u"кафе", u"кафешка", u"закусочная", u"ресторан", u"столовая",
        u"пекарня", u"кондитерская", u"кофейня", u"суши", u"пиццерия",
        u"доставка", u"доставка еды", u"кальян", u"шашлычная", u"лагманная",
        u"лагманхона", u"чайхана", u"чойхона", u"еда", u"кулинария",
        u"кофейный дом", u"кафе-бар", u"рестобар", u"фудкорт",
        u"быстрого питания", u"общепит", u"питание", u"караоке",
        u"клуб", u"тезтайёр", u"тезтайер", u"tez tayyor", u"tezhtayyor",
        u"тарабхона", u"кафедарун", u"тарабхонаи милли", u"суши-бар",
        u"суши-баp", u"фудкорт", u"фуд-корт", u"ресторан быстрого питания",
        u"тест-кафе", u"питей", u"питей-бар", u"бар-кафе",
    )
    by = defaultdict(list)
    for r in rows:
        nm = (r.get("org_name") or "").strip()
        if not nm:
            continue
        low = nm.lower().strip()
        # Если org_name — это ровно родовое слово (или с хвостом-пояснением
        # через запятую, где тоже родовое), пропускаем.
        head = low.split(",")[0].strip()
        if head in GENERIC_NET or low in GENERIC_NET:
            continue
        by[nm].append(r)
    out = []
    for nm, items in by.items():
        if len(items) < 3:
            continue
        site = next((first_site(i) for i in items if first_site(i)), None)
        app = next((first_app(i) for i in items if first_app(i)), None)
        phone = next((first_phone(i) for i in items if first_phone(i)), None)
        sched = next((fmt_hours(i) for i in items
                      if i.get("is_24x7") or i.get("card_is_24x7")), None)
        ratings = [i.get("rating") for i in items if i.get("rating")]
        avg = round(sum(ratings) / len(ratings), 2) if ratings else None
        out.append({"net": nm, "n": len(items), "site": site,
                    "app": app, "phone": phone, "hours": sched, "avg": avg})
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
        out.append((d, items2[:5], len(items)))
    return out


def partition_by_rating(rows):
    hi = [r for r in rows if (r.get("rating") or 0) >= MIN_RATING]
    unknown = [r for r in rows if r.get("rating") is None]
    lo = [r for r in rows
          if r.get("rating") is not None and r["rating"] < MIN_RATING]
    return hi, unknown, lo


def full_list(rows):
    ok = [r for r in rows if r.get("address_name") and r.get("lat")
          and r.get("lon")]
    ok.sort(key=lambda r: (-(r.get("rating") or 0), -(r.get("review_count") or 0),
                           (r.get("name") or "")))
    return ok


def yx_cities(yx):
    by = defaultdict(lambda: [0, None])
    for r in yx:
        city = r.get("city")
        by[city][0] += 1
        by[city][1] = r.get("city_ru") or by[city][1]
    return dict(by)


def load_yx():
    if not os.path.exists(YX_ROWS):
        return []
    out = []
    for line in io.open(YX_ROWS, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("kind") == "list" or r.get("kind") == "org":
            out.append(r)
    return out


def load_yx_block():
    """Готовый блок региональных карточек из `../food_yandex/cards.py`.

    Пока прогон не прошёл, файла нет — и в разделе остаются прямые
    ссылки-поисковики по каталогам.
    """
    if not os.path.exists(YX_BLOCK):
        return u""
    text = io.open(YX_BLOCK, encoding="utf-8").read().strip()
    return text if u"###" in text.splitlines()[0] else u""


def render():
    all_rows = [r for r in load_food() if is_food(r)]
    yx = load_yx()
    yx_block = load_yx_block()
    hi, unknown, lo = partition_by_rating(all_rows)
    shown = hi + unknown  # рейтинг <4 не выводим
    by_cat = defaultdict(list)
    for r in shown:
        by_cat[categorize(r)].append(r)
    networks = top_networks(all_rows)
    dists = per_district_top(all_rows)
    cities = yx_cities(yx)
    total_gis = len(all_rows)
    total_shown = len(shown)
    n4 = len(hi)
    n_unk = len(unknown)
    total_yx = len(yx)

    lines = []
    lines.append(u"### Заведения: бары, кафе, кофейни, чайханы, рестораны, доставка, фудкорты")
    lines.append(u"")
    lines.append(u"_Данные: справочник 2ГИС по Душанбе (широкая SSR-выдача + "
                 u"карточки) и Яндекс.Карты по таджикским каталогам. Собрано "
                 u"скриптами `food_2gis/` и `food_yandex/`. Ниже — все "
                 u"заведения общепита (бары, пабы, кафе, кофейни, чайханы, "
                 u"рестораны, доставка еды, фудкорты) с рейтингом 4.0 и "
                 u"выше; там, где 2ГИС не отдаёт рейтинг (малоизвестные "
                 u"объекты), они идут в общий список без фильтра._")
    lines.append(u"")
    lines.append(u"- **Душанбе**: %d заведений общепита с адресом и "
                 u"координатами; %d с рейтингом 4.0+; %d без рейтинга "
                 u"(малоизвестные). %d сетей (3+ точки), %d с телефоном, "
                 u"%d с сайтом, %d с соцсетями/мессенджерами в карточке." % (
                     total_gis, n4, n_unk, len(networks),
                     sum(1 for r in shown if first_phone(r)),
                     sum(1 for r in shown if first_site(r)),
                     sum(1 for r in shown if socials(r))))
    if total_yx:
        lines.append(u"- **По стране (Яндекс.Карты)**: %d карточек в %d "
                     u"таджикских каталогах." % (total_yx, len(cities)))
    elif yx_block:
        lines.append(u"- **По стране (Яндекс.Карты)**: ниже отдельный блок "
                     u"«Карточки заведений по городам» — те же заведения с "
                     u"координатами, рейтингом, телефоном и адресом. Душанбе "
                     u"там дублирует 2ГИС-списки выше — у Яндекса свои "
                     u"рейтинги и телефоны; остальные города 2ГИС по стране "
                     u"не покрывает вовсе.")
    else:
        lines.append(u"- **По стране (Яндекс.Карты)**: Яндекс на этом заходе "
                     u"закрыл выдачу по таджикским каталогам (троттлинг), "
                     u"по остальным городам даются прямые ссылки-поисковики "
                     u"вида `yandex.kz/maps/<каталог>/search/кафе/` — по "
                     u"каждой открывается полный актуальный список.")
    lines.append(u"- **Координаты и ссылки на карточки**: в таблицах ниже у "
                 u"каждого заведения стоят lon/lat и ссылка на 2GIS-карточку. "
                 u"Там же — телефоны, сайты, соцсети, мессенджеры, приложения.")
    lines.append(u"- **Как читать рейтинг**: 2ГИС считает рейтинг по "
                 u"отзывам; у большинства чайхан/кафе отзывов мало, поэтому "
                 u"в колонке «рейтинг» стоит прочерк, даже если заведение "
                 u"работает давно. Фильтр >=4.0 применяется только там, где "
                 u"рейтинг известен.")
    lines.append(u"")

    if networks:
        lines.append(u"#### Сети заведений Душанбе (3+ точки)")
        lines.append(u"")
        lines.append(u"| Сеть | Точек | Рейтинг (средн.) | Сайт | Телефон | "
                     u"Часы (круглосуточные/обычные) |")
        lines.append(u"|---|---:|---:|---|---|---|")
        for row in networks[:30]:
            site = escape(row["site"]) or u"—"
            phone = escape(row["phone"]) or u"—"
            hours = escape(row["hours"]) or u"—"
            avg = (u"%.1f" % row["avg"]) if row["avg"] else u"—"
            lines.append(u"| %s | %d | %s | %s | %s | %s |" % (
                escape(row["net"]), row["n"], avg, site, phone, hours))
        lines.append(u"")

    if n4:
        lines.append(u"#### Топ заведений по рейтингу (4.0+)")
        lines.append(u"")
        lines.append(u"| Название | Категория | Адрес | Район | Рейтинг | "
                     u"Отзывов | Телефон | Сайт | Соцсети | Координаты | "
                     u"Карточка |")
        lines.append(u"|---|---|---|---|---:|---:|---|---|---|---|---|")
        top = sorted(hi, key=lambda r: (-(r.get("rating") or 0),
                                        -(r.get("review_count") or 0)))
        for r in top[:80]:
            coord = (u"%.6f, %.6f" % (r["lon"], r["lat"])) if r.get("lon") \
                and r.get("lat") else u"—"
            site = first_site(r)
            socs = socials(r)
            lines.append(u"| %s | %s | %s | %s | %.1f | %d | %s | %s | %s | "
                         u"%s | [2GIS](%s) |" % (
                             escape(r.get("name")),
                             escape(categorize(r)),
                             escape(r.get("address_name")),
                             escape(r.get("district")),
                             r.get("rating") or 0,
                             r.get("review_count") or 0,
                             escape(first_phone(r)) or u"—",
                             (u"[сайт](%s)" % site) if site else u"—",
                             (u"[соцсети](%s)" % socs[0]) if socs else u"—",
                             coord,
                             escape(r.get("url_2gis"))))
        lines.append(u"")

    lines.append(u"#### Полный список по типам заведений")
    lines.append(u"")
    cat_order = [u"Чайханы", u"Рестораны", u"Кафе",
                 u"Бары, пабы, караоке и клубы",
                 u"Кофейни и кондитерские",
                 u"Фудкорты и фуд-холлы",
                 u"Доставка еды",
                 u"Прочие заведения"]
    for cat in cat_order:
        items = by_cat.get(cat) or []
        if not items:
            continue
        items = full_list(items)
        lines.append(u"##### %s — %d" % (cat, len(items)))
        lines.append(u"")
        lines.append(u"| Название | Адрес | Район | Часы | Рейтинг | "
                     u"Телефон | Сайт | Соцсети | Координаты | Карточка |")
        lines.append(u"|---|---|---|---|---:|---|---|---|---|---|")
        for r in items:
            coord = (u"%.6f, %.6f" % (r["lon"], r["lat"])) if r.get("lon") \
                and r.get("lat") else u"—"
            site = first_site(r)
            socs = socials(r)
            rating = r.get("rating")
            rstr = (u"%.1f" % rating) if rating else u"—"
            lines.append(u"| %s | %s | %s | %s | %s | %s | %s | %s | %s | "
                         u"[2GIS](%s) |" % (
                             escape(r.get("name")),
                             escape(r.get("address_name")),
                             escape(r.get("district")),
                             escape(fmt_hours(r)),
                             rstr,
                             escape(first_phone(r)) or u"—",
                             (u"[сайт](%s)" % site) if site else u"—",
                             (u"[соцсети](%s)" % socs[0]) if socs else u"—",
                             coord,
                             escape(r.get("url_2gis"))))
        lines.append(u"")

    lines.append(u"#### По районам (топ-5 по рейтингу)")
    lines.append(u"")
    for d, items, n in dists:
        lines.append(u"**%s** — %d заведений" % (escape(d), n))
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
                escape(categorize(r)), tail, escape(r.get("url_2gis"))))
        lines.append(u"")

    if yx_block:
        lines.append(yx_block)
        lines.append(u"")
    else:
        lines.append(u"#### Заведения в остальных городах")
        lines.append(u"")
        lines.append(u"2ГИС по Таджикистану покрывает только Душанбе, поэтому "
                     u"за пределами столицы — Яндекс.Карты. Ниже прямые ссылки "
                     u"на поиск по основным типам заведений в каждом "
                     u"таджикском каталоге.")
        lines.append(u"")
        CITIES = [
            (u"Худжанд", u"10322/khujand"),
            (u"Конибодом", u"116395/konibodom"),
            (u"Исфара", u"101751/isfara"),
            (u"Пенджикент", u"10320/pendjikent"),
            (u"Бохтар", u"10319/bohtar"),
            (u"Куляб", u"20882/kulob"),
            (u"Турсунзаде", u"21107/tursunzoda"),
            (u"Нурек", u"10321/nurek"),
            (u"Гиссар", u"105973/hisor-district"),
            (u"Хорог (ГБАО)", u"37175/horog"),
            (u"Согдийская область", u"105968/sughd-province"),
            (u"Хатлонская область", u"105969/khatlon-province"),
        ]
        QUERIES = [
            (u"Кафе", u"кафе"),
            (u"Рестораны", u"ресторан"),
            (u"Чайханы", u"чайхана"),
            (u"Бары", u"бар"),
            (u"Кофейни", u"кофейня"),
            (u"Доставка еды", u"доставка еды"),
        ]
        from urllib.parse import quote as yq
        header = u"| Город | " + u" | ".join(
            escape(q[0]) for q in QUERIES) + u" |"
        sep = u"|---" * (len(QUERIES) + 1) + u"|"
        lines.append(header)
        lines.append(sep)
        for name, cat in CITIES:
            cells = []
            for _, q in QUERIES:
                url = (u"https://yandex.kz/maps/%s/search/%s"
                       % (cat, yq(q)))
                cells.append(u"[открыть](%s)" % url)
            lines.append(u"| %s | %s |" % (escape(name), u" | ".join(cells)))
        lines.append(u"")

    lines.append(u"#### Практический вывод")
    lines.append(u"")
    lines.append(u"- В Душанбе чайханы и рестораны с фокусом на местную "
                 u"кухню концентрируются на проспектах Исмоили Сомони, "
                 u"Рудаки, Джумабекова и в районах Фирдоуси/Центр; "
                 u"европейские кофейни и бары — вокруг «Гвардейского» "
                 u"пересечения и в новых ЖК Сино/Шохмансур.")
    lines.append(u"- Круглосуточные заведения редки: в основной массе "
                 u"кафе закрываются в 22:00–23:00, чайханы — в 20:00–21:00. "
                 u"Доставка еды (Gfood, Anor, Halto, FoodPax и т. п.) "
                 u"работает до полуночи или 24/7.")
    lines.append(u"- В Худжанде, Кулябе, Бохтаре и Турсунзаде кафе и "
                 u"рестораны есть в центре; в районных центрах ГБАО, "
                 u"Лахша, Раште, Джиргатоло — только чайханы/столовые при "
                 u"автостанциях, и их мало.")
    lines.append(u"- В горных кишлаках (Ягноб, Вахан, Зоркуль, Мургаб) "
                 u"заведений общепита нет; питание — через гестхаус или "
                 u"с собой.")
    lines.append(u"")

    text = "\n".join(lines) + "\n"
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(text)
    print("wrote:", os.path.basename(OUT), len(text), "bytes,",
          "total=%d, shown=%d (4+=%d, unk=%d), networks=%d" % (
              total_gis, total_shown, n4, n_unk, len(networks)))
    return text


if __name__ == "__main__":
    render()
