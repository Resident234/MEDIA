# -*- coding: utf-8 -*-
"""Разложить ссылки-поисковики раздела 11 на карточки аптек.

В разделе 11 стояла таблица ссылок вида
``https://yandex.kz/maps/10322/khujand/search/аптека`` — это поисковая
выдача, а не список. Здесь те же каталожные запросы прогоняются через
HTTP-канал (yxhttp, state-view) и превращаются в списки конкретных карточек:
название · координаты · ссылка на карточку · рейтинг · телефон · адрес — тот
же формат, что у душанбинского блока 2ГИС и у лабораторий рядом.

Запросы: 12 каталогов (10 городов + Согдийская и Хатлонская области, они
добирают районные центры) на 3 формулировки — «аптека», «аптеки» и
«дорухона» (таджикское написание ловит карточки, заведённые не по-русски).
Город карточки берётся из её адреса, а не из каталога: областная выдача
возвращает аптеки по всей области.

usage:
  python cards.py              # добрать несобранное и пересобрать блок
  python cards.py --collect    # только сеть
  python cards.py --render     # только сборка (сеть не трогаем)
  python cards.py --build      # плюс пересобрать travels/Таджикистан.md
  python cards.py --limit 20   # сколько запросов за прогон

Состояние: cards.jsonl (по строке на карточку, с полями _cat/_q) и
queries.ok (по строке на отработанный запрос) — прогон можно прерывать.

Выход cards_block.md подхватывает `pharma_2gis/make_md.py`: если файл есть,
он заменяет собой старую таблицу ссылок в разделе 11.
"""
import io
import json
import os
import re
import sys
import time
import urllib.parse
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(WORK, "housing_yandex"))
import yxhttp  # noqa: E402

# Домен тот же, что у остальных проходов: с чужого IP yandex.com отдаёт
# заглушку «limited» чаще, чем yandex.ru, при том же наборе данных.
HOST = (os.environ.get("YX_HOST") or "https://yandex.ru").rstrip("/")

CARDS = os.path.join(HERE, "cards.jsonl")
DONE = os.path.join(HERE, "queries.ok")
OUT = os.path.join(HERE, "cards_block.md")
STATS = os.path.join(HERE, "cards_stats.json")
LOG = os.path.join(HERE, "cards.log")

MAX_FAIL = 4
BAN_PAUSE = 120
# Областные каталоги отдают тысячи заведений: берём первые страницы по
# релевантности, дальше уже глушь без адресов.
PAGES_CITY = 6
PAGES_REGION = 8
# Населённый пункт с одним-двумя заведениями не тянет на отдельный раздел.
SMALL_MAX = 2

# Каталоги из таблицы раздела 11 (проверены: каждая ссылка открывается).
CATALOGS = [
    (u"Худжанд", u"10322/khujand"),
    (u"Конибодом", u"116395/konibodom"),
    (u"Исфара", u"101751/isfara"),
    (u"Пенджикент", u"10320/pendjikent"),
    (u"Бохтар", u"10319/bohtar"),
    (u"Куляб", u"20882/kulob"),
    (u"Турсунзаде", u"21107/tursunzoda"),
    (u"Нурек", u"10321/nurek"),
    (u"Гиссар", u"105973/hisor-district"),
    (u"Хорог", u"37175/horog"),
    (u"Согдийская область", u"105968/sughd-province"),
    (u"Хатлонская область", u"105969/khatlon-province"),
]
REGIONS = (u"105968/sughd-province", u"105969/khatlon-province")

# «дорухона» — таджикское написание: часть аптек в Яндексе заведена
# только так и по слову «аптека» не находится.
QUERIES = [
    (u"аптека", u"Аптеки"),
    (u"аптеки", u"Аптеки"),
    (u"дорухона", u"Аптеки"),
]

# Рубрика одна: в список идёт только то, что само себя называет аптекой.
# Аптечные пункты при клиниках и медцентрах сюда не подмешиваем — они уже
# есть в разделе про лаборатории.
RUBRICS = [
    (u"Аптеки", (u"аптек", u"аптечн", u"pharmacy", u"pharm", u"дорухон",
                 u"дорихона", u"dorixona")),
]
RUBRIC_ORDER = [r for r, _k in RUBRICS]

# Не аптека: запрос «аптека» тянет ветеринарные аптеки, оптику, зоомагазины
# и аптечные киоски при клиниках. Чёрный список проверяется первым — иначе
# «ветеринарная аптека» прошла бы по слову «аптек».
NON_PHARM = (u"ветеринар", u"зоомагазин", u"зоотовар", u"груминг",
             u"автомойк", u"автосервис", u"автозапчаст", u"шиномонтаж",
             u"азс", u"банк", u"обмен валют", u"страхов", u"нотариус",
             u"юридическ", u"кафе", u"ресторан", u"кальян", u"отель",
             u"гостиниц", u"хостел", u"фитнес", u"тренажерн", u"тренажёрн",
             u"салон", u"парикмах", u"косметик", u"парфюм", u"бытов",
             u"супермаркет", u"магазин продуктов", u"табак", u"алкоголь",
             u"стоматолог", u"dental", u"лаборатор", u"клиник", u"медцентр",
             u"больниц", u"диспансер", u"образован", u"курсы", u"школа")


def stem_re(stem):
    """Начало слова: «аптек» ловит «аптека» и «аптечный», «дорухон» — «дорухона»."""
    return re.compile(u"(?<![0-9a-zа-яё])%s" % stem)


RUBRIC_RE = [(name, [stem_re(w) for w in keys]) for name, keys in RUBRICS]
NON_PHARM_RE = [stem_re(w) for w in NON_PHARM]

# Соседние страны: их заведения попадают в таджикские каталоги (Самарканд — в
# Пенджикент, Кундуз — в Куляб), в раздел по Таджикистану они не идут.
FOREIGN = (u"самарканд", u"ташкент", u"ферган", u"андижан", u"наманган",
           u"бухар", u"кашкадарь", u"сурхандарь", u"джизак", u"хорезм",
           u"навои", u"каракалпак", u"сырдарь", u"узбекистан", u"кыргызстан",
           u"киргизия", u"баткен", u"афганистан", u"кабул", u"кундуз",
           u"талукан", u"мешхед", u"иран", u"кашгар", u"пакистан")
REGION_WORDS = (u"область", u"вилоят", u"автономная", u"республик",
                u"районы республиканского", u"таджикистан", u"тоҷикистон")
SETTLE_PREFIX = (u"посёлок городского типа ", u"поселок городского типа ",
                 u"городского типа ", u"джамоат посёлка ", u"джамоат ",
                 u"город ", u"г. ", u"посёлок ",
                 u"поселок ", u"пгт. ", u"пгт ", u"село ", u"деҳа ", u"деха ",
                 u"кишлак ", u"махалля ")

# Как Яндекс пишет одно и то же место по-разному.
CANON = {
    u"худжанд": u"Худжанд", u"хуҷанд": u"Худжанд", u"ходжент": u"Худжанд",
    u"канибадам": u"Конибодом", u"конибодом": u"Конибодом",
    u"исфара": u"Исфара", u"исфара, ": u"Исфара",
    u"пенджикент": u"Пенджикент", u"панҷакент": u"Пенджикент",
    u"панджакент": u"Пенджикент",
    u"бохтар": u"Бохтар", u"курган-тюбе": u"Бохтар", u"қӯрғонтеппа": u"Бохтар",
    u"кульаб": u"Куляб", u"кулоб": u"Куляб", u"кӯлоб": u"Куляб",
    u"куляб": u"Куляб",
    u"турсунзаде": u"Турсунзаде", u"турсунзода": u"Турсунзаде",
    u"нурек": u"Нурек", u"норак": u"Нурек",
    u"гиссар": u"Гиссар", u"хисор": u"Гиссар", u"ҳисор": u"Гиссар",
    u"хорог": u"Хорог", u"хоруғ": u"Хорог",
    u"истаравшан": u"Истаравшан", u"ура-тюбе": u"Истаравшан",
    u"ӯротеппа": u"Истаравшан",
    u"гулистон": u"Гулистон", u"каяккум": u"Гулистон",
    u"бустон": u"Бустон", u"чкаловск": u"Бустон",
    u"левакант": u"Левакант", u"сарбанд": u"Левакант",
    u"душанбе": u"Душанбе",
    # Районные центры Согда и Хатлона: областные каталоги отдают их пачками,
    # и без приведения к одному написанию они расползаются на два-три раздела.
    u"гафуров": u"Гафуров",
    u"ашт": u"Ашт", u"аштский район": u"Аштский район",
    u"зафаробод": u"Зафарабад", u"зафарабад": u"Зафарабад",
    u"шахристон": u"Шахристон", u"шахристан": u"Шахристон",
    u"деваштич": u"Деваштич", u"спитамен": u"Спитамен",
    u"джаббор расулов": u"Джаббор Расулов",
    u"джаббор расуловский район": u"Джаббор Расулов",
    u"мастчох": u"Мастчох", u"кухистони мастчох": u"Мастчох",
    u"айни": u"Айни", u"вахдат": u"Вахдат", u"кофарнихон": u"Вахдат",
    u"рогун": u"Рогун", u"дангара": u"Дангара",
    u"фархор": u"Фархор", u"пархар": u"Фархор",
    u"восе": u"Восе", u"восеъ": u"Восе", u"хамадони": u"Хамадони",
    u"муминабад": u"Муминабад", u"шамсиддин шохин": u"Шамсиддин Шохин",
    u"кубодиён": u"Кубодиён", u"кабадиан": u"Кубодиён",
    u"шаартуз": u"Шаартуз", u"носири хусрав": u"Носири Хусрав",
    u"джайхун": u"Джайхун", u"яван": u"Яван", u"хуросон": u"Хуросон",
    u"джиликуль": u"Джиликуль", u"джиликул": u"Джиликуль",
    u"балджувон": u"Балджувон",
    # «Гиссар с административной территорией» — тот же Гиссар, только с
    # припиской; иначе город делится на два раздела.
    u"гиссар с административной территорией": u"Гиссар",
}
# Города, которые идут первыми и в том же порядке, что строки старой таблицы.
CITY_ORDER = [nm for nm, _c in CATALOGS if _c not in REGIONS]

# Улица в слоте населённого пункта значит, что город в адресе не указан —
# такие карточки в блок не берём (привязывать их к городу запроса нельзя).
STREET_RE = re.compile(
    u"^(ул\\.|улица|просп|проспект|пер\\.|переулок|кӯчаи|кучаи|маҳалла|"
    u"махалля|мкр|микрорайон|шоссе|тупик|пл\\.|площадь|бульвар|наб\\.|тракт)",
    re.I)
# Коды джамоатов вместо названия («РҶ048», «Мд02»): по ним город не прочитать.
CODE_RE = re.compile(u"^\\D{1,3}\\d{1,3}$", re.I)
# Соседние страны — только в начале строки адреса: «Ташкентский проспект» в
# Худжанде не должен отправлять карточку в Узбекистан.
FOREIGN_RE = re.compile(u"(?<![0-9a-zа-яё])(?:%s)" % u"|".join(FOREIGN))


def a(text):
    """Печать в консоль: в CP866 кириллица иначе превращается в мусор."""
    return (text or u"").encode("unicode_escape", "replace").decode("ascii")


def log(line):
    line = u"%s %s" % (time.strftime("%H:%M:%S"), line)
    print(a(line))
    with io.open(LOG, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + u"\n")


def search_url(cat, q):
    return u"%s/maps/%s/search/%s/" % (HOST, cat, urllib.parse.quote(q))


def done_set():
    if not os.path.exists(DONE):
        return set()
    return set(l.strip() for l in io.open(DONE, encoding="utf-8") if l.strip())


def is_pharm(it):
    """Аптека: рубрика из белого списка и не из чёрного.

    Категорий у аптеки обычно две-три («Аптека», «Медицинские товары»),
    поэтому чёрный список смотрим по всем сразу: иначе «Ветеринарная
    аптека» прошла бы по слову «аптек».
    """
    if it.get("type") not in (None, u"business"):
        return False
    texts = []
    for c in it.get("categories") or []:
        texts.append((c.get("name") or u"").lower())
        texts.append((c.get("seoname") or u"").lower().replace(u"_", u" "))
    texts = [t for t in texts if t]
    for t in texts:
        for pat in NON_PHARM_RE:
            if pat.search(t):
                return False
    for t in texts:
        for _rub, pats in RUBRIC_RE:
            for pat in pats:
                if pat.search(t):
                    return True
    if texts:
        return False
    # Категорий нет вовсе — тогда только по названию, и по тем же правилам.
    title = (it.get("title") or u"").lower()
    if any(pat.search(title) for pat in NON_PHARM_RE):
        return False
    return any(pat.search(title) for _rub, pats in RUBRIC_RE for pat in pats)


def rubric_of(rec):
    """Рубрика карточки — первая подходящая по списку категорий."""
    texts = []
    for c in rec.get("categories") or []:
        texts.append((c.get("name") or u"").lower())
        texts.append((c.get("seoname") or u"").lower().replace(u"_", u" "))
    for rub, pats in RUBRIC_RE:
        for t in texts:
            if not t:
                continue
            for pat in pats:
                if pat.search(t):
                    return rub
    return u"Аптеки"


def norm_part(part):
    low = (part or u"").strip().lower()
    for pre in SETTLE_PREFIX:
        if low.startswith(pre):
            low = low[len(pre):]
    return low.strip(u" .")


def is_region(low):
    return any(w in low for w in REGION_WORDS)


def city_of(rec):
    """Город из адреса карточки; None — чужая страна или адрес без города."""
    full = rec.get("fullAddress") or rec.get("address") or u""
    parts = [p.strip() for p in full.split(u",") if p.strip()]
    for part in parts[:3]:
        low = part.lower()
        if is_region(low):
            if FOREIGN_RE.search(low):
                return None
            continue
        if STREET_RE.match(part):
            return None
        name = norm_part(part)
        if not name:
            continue
        if CODE_RE.match(name) or FOREIGN_RE.search(name):
            return None
        # «Большой памирский тракт» — это дорога, а не населённый пункт.
        if u"тракт" in name:
            return None
        canon = CANON.get(name)
        if canon:
            return canon
        # «Район Рудаки» читается как «Рудаки (район)»: так не путается с
        # посёлком Рудаки под Душанбе.
        if name.startswith(u"район "):
            rest = name[len(u"район "):].strip()
            if rest:
                return rest[:1].upper() + rest[1:] + u" (район)"
        # «Имени Дустмурода Алиева» — район, названный в честь человека:
        # Яндекс пишет его строчными, в оглавлении это режет глаз.
        if name.startswith(u"имени "):
            return u"Имени " + u" ".join(
                w[:1].upper() + w[1:]
                for w in name[len(u"имени "):].split())
        # «Гафуровский район», «Джаббор Расуловский район» — так и оставляем:
        # это не город, и приписывать его к Худжанду нельзя.
        return name[:1].upper() + name[1:]
    return None


def collect(limit=None):
    done = done_set()
    todo = []
    for name, cat in CATALOGS:
        for q, _rub in QUERIES:
            key = u"%s|%s" % (cat, q)
            if key not in done:
                todo.append((name, cat, q, key))
    log(u"collect: catalogs=%d queries=%d done=%d todo=%d"
        % (len(CATALOGS), len(CATALOGS) * len(QUERIES), len(done), len(todo)))
    fh = io.open(CARDS, "a", encoding="utf-8", newline="\n")
    dfh = io.open(DONE, "a", encoding="utf-8", newline="\n")
    fails = worked = kept = 0
    for name, cat, q, key in todo:
        url = search_url(cat, q)
        pages = PAGES_REGION if cat in REGIONS else PAGES_CITY
        try:
            kind, items, total, _, complete = yxhttp.harvest(
                url, pages=pages, pause=2)
        except Exception as exc:  # noqa: BLE001 - 404 и прочее не рвут проход
            log(u"error on %s/%s: %s" % (cat, a(q), a(str(exc))[:120]))
            fails += 1
            if fails >= MAX_FAIL:
                log(u"stop: %d errors in a row" % fails)
                break
            continue
        if kind == u"throttled":
            log(u"throttled on %s/%s, wait %ds" % (cat, a(q), BAN_PAUSE))
            time.sleep(BAN_PAUSE)
            try:
                kind, items, total, _, complete = yxhttp.harvest(
                    url, pages=pages, pause=2)
            except Exception:  # noqa: BLE001
                pass
        if kind == u"throttled":
            fails += 1
            if fails >= MAX_FAIL:
                log(u"stop: %d throttles in a row" % fails)
                break
            continue
        fails = 0
        got = 0
        for it in items:
            if not is_pharm(it) or not it.get("id"):
                continue
            rec = dict(it)
            rec[u"_cat"] = name
            rec[u"_q"] = q
            fh.write(json.dumps(rec, ensure_ascii=False) + u"\n")
            got += 1
        fh.flush()
        dfh.write(key + u"\n")
        dfh.flush()
        worked += 1
        kept += got
        log(u"[%03d/%03d] %-26s %-13s %-8s items=%3d kept=%3d total=%s"
            % (worked, len(todo), a(cat)[:26], a(q), kind, len(items), got,
               total))
        if limit and worked >= limit:
            log(u"limit reached")
            break
    fh.close()
    dfh.close()
    log(u"collect done: queries=%d kept=%d" % (worked, kept))


def load_cards():
    """id -> карточка; поля добираются из всех запросов, где она попалась."""
    recs, order = {}, []
    if not os.path.exists(CARDS):
        return recs, order
    for line in io.open(CARDS, encoding="utf-8"):
        if not line.strip():
            continue
        it = json.loads(line)
        iid = it.get("id")
        if not iid:
            continue
        rec = recs.get(iid)
        if rec is None:
            rec = {u"id": iid, u"_cats": []}
            recs[iid] = rec
            order.append(iid)
        for f in (u"title", u"seoname", u"address", u"fullAddress",
                  u"coordinates", u"phones", u"urls", u"socialLinks",
                  u"ratingData", u"categories", u"workingTimeText"):
            if rec.get(f) in (None, u"", [], {}) and it.get(f) not in (
                    None, u"", [], {}):
                rec[f] = it.get(f)
        if it.get(u"_cat") not in rec[u"_cats"]:
            rec[u"_cats"].append(it.get(u"_cat"))
    return recs, order


def site_of(rec):
    for u in rec.get("urls") or []:
        s = u.get("url") if isinstance(u, dict) else u
        if not s or "yandex" in s or "2gis" in s:
            continue
        if s.startswith("http"):
            return s
    return None


def phone_of(rec):
    out = []
    for p in rec.get("phones") or []:
        num = p.get("number") or p.get("value")
        if num and num not in out:
            out.append(num)
    return out


def plural(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return one
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return few
    return many


def card_url(rec):
    seo, iid = rec.get("seoname"), rec.get("id")
    if seo:
        return u"%s/maps/org/%s/%s/" % (HOST, seo, iid)
    return u"%s/maps/org/%s/" % (HOST, iid)


def clean_addr(rec, city):
    """Адрес без области и города — в строке уже стоит раздел города."""
    parts = []
    for part in (rec.get("address") or u"").split(u","):
        part = part.strip()
        if not part:
            continue
        low = part.lower()
        if is_region(low) or norm_part(part) == city.lower():
            continue
        parts.append(part)
    return u", ".join(parts)


def rating_of(rec):
    rating = rec.get("ratingData") or {}
    if rating.get("ratingValue") and rating.get("ratingCount", 0) >= 3:
        return rating["ratingValue"], rating["ratingCount"]
    return None, 0


def row_of(rec, city):
    parts = [u"- **%s**" % (rec.get("title") or u"?")]
    if rec.get("coordinates"):
        lon, lat = rec["coordinates"]
        parts.append(u"· %.6f, %.6f" % (lat, lon))
    parts.append(u"· [Яндекс](%s)" % card_url(rec))
    site = site_of(rec)
    if site:
        parts.append(u"· [сайт](%s)" % site)
    phones = phone_of(rec)
    if phones:
        parts.append(u"· тел. %s" % u", ".join(phones[:2]))
    value, count = rating_of(rec)
    if value:
        parts.append(u"· ★ %.1f (%d)" % (value, count))
    addr = clean_addr(rec, city)
    if addr:
        parts.append(u"· _(%s)_" % addr)
    return u" ".join(parts)


def rows_of(by_rub, city):
    """Строки одного населённого пункта: рубрики по порядку, внутри — по рейтингу."""
    out = []
    for rub in RUBRIC_ORDER:
        arr = by_rub.get(rub) or []
        if not arr:
            continue
        arr.sort(key=lambda r: (-(rating_of(r)[0] or 0), -rating_of(r)[1],
                                (r.get("title") or u"").lower()))
        out.append(u"_**%s** (%d)_" % (rub, len(arr)))
        out.append(u"")
        for rec in arr:
            out.append(row_of(rec, city))
        out.append(u"")
    return out


def total_of(by_rub):
    return sum(len(v) for v in by_rub.values())


def head_of(by_rub, city):
    total = total_of(by_rub)
    return u"**%s** — %d %s" % (
        city, total,
        plural(total, u"аптека", u"аптеки", u"аптек"))


def render():
    recs, order = load_cards()
    if not recs:
        raise SystemExit("no cards in cards.jsonl — run --collect first")

    cities = defaultdict(lambda: defaultdict(list))
    seen, dropped = set(), 0
    for iid in order:
        rec = recs[iid]
        if not rec.get("coordinates"):
            dropped += 1
            continue
        city = city_of(rec)
        if not city:
            dropped += 1
            continue
        key = ((rec.get("title") or u"").lower(),
               tuple(round(v, 5) for v in rec["coordinates"]))
        if key in seen:
            continue
        seen.add(key)
        cities[city][rubric_of(rec)].append(rec)

    all_recs = [r for by in cities.values() for arr in by.values() for r in arr]
    ncards = len(all_recs)
    rated = sum(1 for r in all_recs if rating_of(r)[0])
    phones = sum(1 for r in all_recs if phone_of(r))
    sites = sum(1 for r in all_recs if site_of(r))
    # Сначала города из старой таблицы — в том же порядке, потом прочие
    # районные центры, которые добрали областные каталоги, от крупных к мелким.
    names = [n for n in CITY_ORDER if n in cities]
    rest = [n for n in cities if n not in CITY_ORDER]
    rest.sort(key=lambda n: (-total_of(cities[n]), n))
    names += rest
    # Душанбе — первым: он пересекается с 2ГИС-списком выше, но так видно,
    # что именно Яндекс добавляет к справочнику.
    if u"Душанбе" in names:
        names.remove(u"Душанбе")
        names.insert(0, u"Душанбе")
    # Посёлки с одной-двумя аптеками не стоят отдельного раздела: их
    # собираем под общий кат в конце, иначе блок превращается в оглавление.
    small = [n for n in names if total_of(cities[n]) <= SMALL_MAX]
    names = [n for n in names if n not in small]

    lines = [u"#### Карточки аптек по городам (Яндекс.Карты)", u""]
    lines.append(
        u"_Источник: Яндекс.Карты, съём %s. Ссылки-поисковики «аптека» "
        u"по каталогам разобраны до карточек: название, координаты, ссылка на "
        u"карточку, рейтинг, телефон, адрес. Всего **%d** %s в **%d** %s "
        u"(города и районные центры); рейтинг (от 3 отзывов) — у %d, "
        u"телефон — у %d, свой сайт — у %d. По Душанбе список собран из "
        u"областных каталогов и пересекается с 2ГИС выше — на полноту он не "
        u"претендует, зато у столичных аптек видны рейтинги и телефоны "
        u"Яндекса. За пределами столицы это единственный список с привязкой "
        u"к карте; областные каталоги Согда и Хатлона добирают районные "
        u"центры, которых нет отдельными каталогами._"
        % (time.strftime("%Y-%m-%d"), ncards,
           plural(ncards, u"аптека", u"аптеки", u"аптек"),
           len(names) + len(small),
           plural(len(names) + len(small), u"населённом пункте",
                  u"населённых пунктах", u"населённых пунктах"),
           rated, phones, sites))
    lines.append(u"")

    for city in names:
        lines.append(u"<details><summary>%s</summary>" % head_of(cities[city],
                                                                 city))
        lines.append(u"")
        lines.extend(rows_of(cities[city], city))
        lines.append(u"</details>")
        lines.append(u"")

    if small:
        total = sum(total_of(cities[n]) for n in small)
        lines.append(
            u"<details><summary>**Малые населённые пункты** — %d %s в %d %s"
            u"</summary>" % (total,
                             plural(total, u"аптека", u"аптеки",
                                     u"аптек"), len(small),
                             plural(len(small), u"пункте", u"пунктах",
                                     u"пунктах")))
        lines.append(u"")
        for city in small:
            lines.append(head_of(cities[city], city))
            lines.append(u"")
            lines.extend(rows_of(cities[city], city))
        lines.append(u"</details>")
        lines.append(u"")

    # Каталог, по которому Яндекс не вернул ни одной карточки: без этой
    # строки город просто исчезает из раздела.
    empty = [nm for nm, cat in CATALOGS if cat not in REGIONS and nm not in cities]
    if empty:
        lines.append(u"_**Пусто:**_ %s — Яндекс на все три запроса "
                     u"(«аптека», «аптеки», «дорухона») не вернул ни одной "
                     u"карточки в этом каталоге; ближайшие аптеки — в "
                     u"Душанбе и Худжанде." % u", ".join(empty))
        lines.append(u"")

    text = u"\n".join(lines).rstrip() + u"\n"
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(text)
    # Сводка для генератора раздела 11: он цитирует те же цифры, что и блок,
    # и не пересчитывает их по markdown.
    stats = {u"cards": ncards, u"localities": len(names) + len(small),
             u"rated": rated, u"phones": phones, u"sites": sites,
             u"empty": empty, u"date": time.strftime("%Y-%m-%d")}
    io.open(STATS, "w", encoding="utf-8", newline="\n").write(
        json.dumps(stats, ensure_ascii=False, indent=1) + u"\n")
    print(u"block: %d cards, %d sections (+%d small), dropped=%d -> %s "
          u"(%d bytes)"
          % (ncards, len(names), len(small), dropped, os.path.basename(OUT),
             len(text)))
    return text


def main():
    args = sys.argv[1:]
    limit = None
    for i, arg in enumerate(args):
        if arg == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
            break
    if "--render" not in args:
        collect(limit=limit)
    if "--collect" in args:
        return
    render()
    if "--build" in args:
        import subprocess
        subprocess.call([sys.executable, "build.py"], cwd=WORK)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
