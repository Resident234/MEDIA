# -*- coding: utf-8 -*-
"""Разложить ссылки «Яндекс-поиск» из блока OSM на карточки организаций.

В региональном блоке раздела 5 у каждого салона стояла ссылка вида
``https://yandex.com/maps/?text=Tcell%20Бохтар`` — это поисковая выдача, а не
карточка. Здесь те же запросы прогоняются через HTTP-канал (yxhttp, state-view)
и превращаются в списки конкретных организаций: имя · координаты · ссылка на
карточку · адрес · телефон — тот же формат, что у душанбинского блока 2ГИС.

Запросы на город: по марке каждому оператору, который есть в OSM-блоке этого
города, плюс общий «салон связи <город>» — он добирает лавки без бренда.

usage:
  python cards.py              # добрать несобранное и пересобрать блок
  python cards.py --collect    # только сеть
  python cards.py --render     # только сборка (сеть не трогаем)
  python cards.py --build      # плюс пересобрать travel/Таджикистан.md
  python cards.py --limit 20   # сколько запросов за прогон

Состояние: cards.jsonl (по строке на карточку, с полями _city/_q) и
queries.ok (по строке на отработанный запрос) — прогон можно прерывать.
"""
import io
import json
import math
import os
import re
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(WORK, "housing_yandex"))
import yxhttp  # noqa: E402
from cities import CITIES  # noqa: E402

# Домен тот же, что у жилищного прохода: с чужого IP yandex.com отдаёт заглушку
# «limited» чаще, чем yandex.ru, при том же наборе данных.
HOST = (os.environ.get("YX_HOST") or "https://yandex.ru").rstrip("/")

# Каталог города у Яндекса живёт только под числовым id региона
# (``/maps/10319/bohtar/search/<q>/``); голый слаг отдаёт 404. Идентификаторы
# уже добыты жилищным проходом — берём их оттуда, а для городов, которых там
# нет, узнаём перенаправлением общего поиска и складываем в _catalogs.json.
TOWNS = os.path.join(WORK, "housing_yandex", "_towns.json")
CATS = os.path.join(HERE, "_catalogs.json")
LL = dict((nm, (lon, lat)) for nm, _s, lon, lat, _r in CITIES)

OSM = os.path.join(WORK, "telecom_osm", "rows_osm.jsonl")
SRC_BLOCK = os.path.join(WORK, "telecom_osm", "regional_block.md")
OUT = os.path.join(HERE, "cards_block.md")
DST = os.path.join(WORK, "build", "45_svyaz.md")
CARDS = os.path.join(HERE, "cards.jsonl")
DONE = os.path.join(HERE, "queries.ok")
LOG = os.path.join(HERE, "cards.log")

BEGIN = u"<!-- TELECOM_YX_BLOCK_BEGIN -->"
END = u"<!-- TELECOM_YX_BLOCK_END -->"
# Старый OSM-блок остаётся висеть, если его не снять: режем оба.
OLD_BEGIN = u"<!-- TELECOM_REG_BLOCK_BEGIN -->"
OLD_END = u"<!-- TELECOM_REG_BLOCK_END -->"

# Города, которые уже закрыты 2ГИС-проходом (см. insert_regional.py).
SKIP_CITY = (u"Душанбе", u"Куйбышевский", u"Гиссар")
NO_POINT_CITY = u"Вне населённых пунктов"

# «Билайн» Яндекс в регионах уже не знает (проверено на Бохтаре и Худжанде:
# пустая выдача), а «Зет-Мобайл» отдаёт те же салоны — марка переименована.
OP_QUERY = [
    (u"Tcell", u"Tcell"),
    (u"МегаФон", u"МегаФон"),
    (u"Зет-Мобайл (ex-Beeline)", u"Зет-Мобайл"),
    (u"Бабилон", u"Бабилон"),
    (u"Тоҷиктелеком", u"Тоҷиктелеком"),
]
OP_ORDER = [u"Tcell", u"МегаФон", u"Зет-Мобайл (ex-Beeline)", u"Бабилон",
            u"Тоҷиктелеком", u"Анор", u"O-Mobile", u"Норак (MTT)", u"ИндигО",
            u"Мобайл+", u"Прочие салоны"]
# Рубрики, которые вообще считаем салоном связи: у Яндекса все они в классе
# mobile phones, у проводного телекома класс другой — поэтому ещё и по имени.
TELECOM_SEO = (u"mobile_phone_store", u"mobile_network_operator",
               u"telecommunication_company", u"internet_service_provider",
               u"telephone_exchange", u"cellular_communication")
TELECOM_NAME = (u"связ", u"телеком", u"оператор", u"мобил", u"интернет",
                u"telecom", u"mobile")
BRANDS = [
    (u"Tcell", (r"tcell", r"tsell", r"тселл", r"тиселл", r"тиҷселл")),
    (u"МегаФон", (r"мегафон", r"megafon", r"megaphone", r"mega\s?fon")),
    (u"Зет-Мобайл (ex-Beeline)", (r"zet[-\s]?mobile", r"зет", r"beeline",
                                  r"билайн")),
    (u"Бабилон", (r"babilon", r"бабилон", r"вавилон", r"vavilon")),
    (u"Тоҷиктелеком", (r"тоҷиктелеком", r"таджиктелеком", r"tojiktelecom",
                       r"tadzhiktelekom")),
    (u"ИндигО", (r"индиго", r"indigo")),
    (u"Анор", (r"анор", r"anor")),
    # Без границ слова «o mobile» ловит «Allo Mobile», а «o-мобайл» — соседей по
    # алфавиту вроде «Номобайл», поэтому только отдельным словом.
    (u"O-Mobile", (r"o[-\s]?mobile", r"o[-\s]?мобайл")),
]
BRAND_RE = [(op, re.compile(u"|".join(
    u"(?<![0-9a-zа-яё])%s(?![0-9a-zа-яё])" % p for p in pats)))
    for op, pats in BRANDS]
ALIAS = {
    u"Бохтар": (u"бохтар", u"курган-тюбе", u"қурғонтеппа", u"кургантюбе"),
    u"Худжанд": (u"худжанд", u"хуҷанд", u"ходжент"),
    u"Хорог": (u"хорог", u"хоруғ"),
    u"Куляб": (u"кулоб", u"кӯлоб", u"куляб"),
    u"Истаравшан": (u"истаравшан", u"ура-тюбе", u"ӯротеппа"),
    u"Пенджикент": (u"пенджикент", u"панҷакент"),
    u"Нурек": (u"нурек", u"норак"),
    u"Канибадам": (u"канибадам", u"конибодом"),
    u"Турсунзаде": (u"турсунзаде", u"турсунзода"),
    u"Мургаб": (u"мургаб", u"мурғоб"),
    u"Ишкашим": (u"ишкашим", u"ишкошим"),
    u"Рошткала": (u"рошткала", u"роштқалъа"),
    u"Вахан": (u"вахан", u"вахон"),
    u"Пархар": (u"пархар", u"фархор"),
    u"Шамсиддин-Один": (u"шамсиддин-один", u"шамсиддин шохин"),
}
REGION_WORDS = (u"область", u"вилоят", u"районы республиканского подчинения",
                u"район", u"таджикистан", u"тоҷикистон")
STREET_RE = re.compile(u"^(кӯчаи|кучаи|улица|ул\\.|проспект|просп\\.|маҳалла|"
                       u"махалла|деҳа|село)\\s", re.I)
MAX_FAIL = 4
BAN_PAUSE = 120
MAX_KM = 35.0
# «Адрес молчит» — доверяем геометрии только в пределах города.
NEAR_KM = 25.0
OSM_MATCH_M = 80.0
# Ссылку на OSM ставим, только когда точки совпали в пределах дома.
OSM_LINK_KM = 0.025
# Душанбе и пригороды уже закрыты блоком 2ГИС: их карточки в регионы не берём.
OFF_CITY = (u"душанбе", u"куйбышевский", u"гиссар", u"кофарнихон")


def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def log(msg):
    line = "[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    sys.stdout.write(a(line))
    sys.stdout.flush()
    io.open(LOG, "a", encoding="utf-8").write(line)


def km(lon1, lat1, lon2, lat2):
    dx = (lon1 - lon2) * math.cos(math.radians((lat1 + lat2) / 2.0)) * 111.32
    dy = (lat1 - lat2) * 110.57
    return math.hypot(dx, dy)


def load_osm():
    """(города по убыванию размера OSM-блока, точки) — Душанбе уже не наш."""
    rows = [json.loads(l) for l in io.open(OSM, encoding="utf-8") if l.strip()]
    rows = [r for r in rows
            if not any((r.get("city") or "").startswith(s) for s in SKIP_CITY)]
    # В OSM иногда под оператора размечена улица («кӯчаи Клары Зеткин») — это
    # не салон, в списке ей не место.
    rows = [r for r in rows
            if not STREET_RE.match(r.get("name") or u"")]
    for r in rows:
        if not r.get("city"):
            r["city"] = NO_POINT_CITY
        # «Пенджикент (окр.)» — точки района вокруг города; в путеводителе это
        # тот же город, отдельный заголовок только двоил бы список.
        r["city"] = re.sub(r"\s*\(окр\.\)\s*$", u"", r["city"])
    by_city = {}
    for r in rows:
        by_city.setdefault(r["city"], []).append(r)
    order = sorted(by_city, key=lambda c: (-len(by_city[c]), c))
    return order, by_city, rows


def city_base(label):
    return label.split(u" (")[0]


def search_url(q):
    return u"https://yandex.com/maps/?text=" + urllib.parse.quote(q)


def prefix_of(url):
    """``.../10319/bohtar/search/<q>/`` -> ``.../10319/bohtar/search/``."""
    if not url or "/search/" not in url:
        return None
    return url.split("/search/")[0] + "/search/"


def load_cats():
    """Город -> префикс каталога: сперва жилищный справочник, потом наш."""
    cats = {}
    for path in (TOWNS, CATS):
        if not os.path.exists(path):
            continue
        try:
            data = json.load(io.open(path, encoding="utf-8"))
        except ValueError:
            continue
        for name, url in data.items():
            pre = prefix_of(url)
            if pre:
                cats.setdefault(name, pre)
    return cats


def discover(label, cats):
    """Узнать каталог города перенаправлением общего поиска.

    Общий ``?text=`` у Яндекса мировой (на «МегаФон Мургаб» отдаёт Мешхед и
    Термез), но если у пункта есть каталог, Яндекс сам перебрасывает туда — из
    адреса после переброса и берётся префикс. Точка ``ll`` нужна, чтобы
    одноимённые кишлаки по соседству не увели переброс в чужой город.
    """
    base = city_base(label)
    url = search_url(base)
    ll = LL.get(base)
    if ll:
        url += u"&ll=%.4f,%.4f&z=13" % ll
    try:
        _, final = yxhttp._get(url)
    except Exception:  # noqa: BLE001 - город просто останется без каталога
        return None
    pre = prefix_of(final)
    if not pre:
        return None
    cats[base] = pre
    try:
        old = json.load(io.open(CATS, encoding="utf-8"))
    except (IOError, OSError, ValueError):
        old = {}
    old[base] = pre
    io.open(CATS, "w", encoding="utf-8", newline="\n").write(
        json.dumps(old, ensure_ascii=False, indent=1, sort_keys=True))
    return pre


def catalog_url(label, q, cats):
    """Адрес поиска внутри каталога города, если каталог известен."""
    pre = cats.get(city_base(label))
    if not pre:
        return None
    return pre + urllib.parse.quote(q) + "/"


def viewport_url(label, q):
    """Поиск по карте вокруг центра пункта — для городов без своего каталога."""
    url = search_url(u"%s %s" % (q, city_base(label)))
    ll = LL.get(city_base(label))
    if ll:
        url += u"&ll=%.4f,%.4f&z=13" % ll
    return url


def queries_for(label, items, cats):
    """Запросы города: марки, что есть в OSM-блоке, плюс общий «салон связи»."""
    out = []
    if label == NO_POINT_CITY:
        return out
    ops = set(r.get("operator") for r in items)
    for op, qname in OP_QUERY:
        if op in ops:
            out.append(qname)
    out.append(u"салон связи")
    res = []
    for q in out:
        url = catalog_url(label, q, cats)
        mode = u"cat" if url else u"map"
        if not url:
            url = viewport_url(label, q)
        res.append((u"%s|%s|%s" % (label, q, mode), q, url))
    return res


def done_set():
    if not os.path.exists(DONE):
        return set()
    return set(l.strip() for l in io.open(DONE, encoding="utf-8") if l.strip())


def is_telecom(it):
    if it.get("type") not in (None, u"business"):
        return False
    cats = it.get("categories") or []
    for c in cats:
        seo = (c.get("seoname") or u"").lower()
        name = (c.get("name") or u"").lower()
        if seo in TELECOM_SEO or (c.get("class") or u"") == u"mobile phones":
            return True
        if any(w in name for w in TELECOM_NAME):
            return True
    return False


def collect(limit=None):
    order, by_city, _ = load_osm()
    cats = load_cats()
    for label in order:
        base = city_base(label)
        if label == NO_POINT_CITY or base in cats:
            continue
        pre = discover(label, cats)
        log("catalog %-24s %s" % (a(base), a(pre or "none (viewport search)")))
    done = done_set()
    todo = []
    for label in order:
        for qkey, q, url in queries_for(label, by_city[label], cats):
            if qkey not in done:
                todo.append((label, qkey, q, url))
    log("collect: cities=%d queries=%d done=%d todo=%d catalogs=%d"
        % (len(order), sum(len(queries_for(l, by_city[l], cats)) for l in order),
           len(done), len(todo), len(cats)))
    fh = io.open(CARDS, "a", encoding="utf-8", newline="\n")
    dfh = io.open(DONE, "a", encoding="utf-8", newline="\n")
    fails = worked = kept = 0
    for label, qkey, q, url in todo:
        try:
            kind, items, total, _, complete = yxhttp.harvest(url, pages=3,
                                                             pause=2)
        except Exception as exc:  # noqa: BLE001 - 404 и прочее не рвут проход
            log("error on %s: %s" % (a(q), a(str(exc))[:120]))
            fails += 1
            if fails >= MAX_FAIL:
                log("stop: %d errors in a row" % fails)
                break
            continue
        if kind == "throttled":
            log("throttled on %s, wait %ds" % (a(q), BAN_PAUSE))
            time.sleep(BAN_PAUSE)
            try:
                kind, items, total, _, complete = yxhttp.harvest(
                    url, pages=3, pause=2)
            except Exception:  # noqa: BLE001
                pass
        if kind == "throttled":
            fails += 1
            if fails >= MAX_FAIL:
                log("stop: %d throttles in a row" % fails)
                break
            continue
        fails = 0
        got = 0
        for it in items:
            if not is_telecom(it) or not it.get("id"):
                continue
            rec = dict(it)
            rec["_city"] = label
            rec["_q"] = q
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            got += 1
        fh.flush()
        dfh.write(qkey + "\n")
        dfh.flush()
        worked += 1
        kept += got
        log("[%03d/%03d] %-52s %-8s items=%2d kept=%2d total=%s"
            % (worked, len(todo), a(q)[:52], kind, len(items), got, total))
        if limit and worked >= limit:
            log("limit reached")
            break
    fh.close()
    dfh.close()
    log("collect done: queries=%d kept=%d" % (worked, kept))


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
            rec = {"id": iid, "_cities": [], "_qs": []}
            recs[iid] = rec
            order.append(iid)
        rec.setdefault("title", it.get("title"))
        rec.setdefault("seoname", it.get("seoname"))
        for f in ("address", "fullAddress", "coordinates", "phones", "urls",
                  "socialLinks", "ratingData", "categories", "workingTimeText"):
            if rec.get(f) in (None, u"", [], {}) and it.get(f) not in (
                    None, u"", [], {}):
                rec[f] = it.get(f)
        for c in it.get("_cities") or []:
            if c not in rec["_cities"]:
                rec["_cities"].append(c)
        if it.get("_city") and it["_city"] not in rec["_cities"]:
            rec["_cities"].append(it["_city"])
        if it.get("_q"):
            rec["_qs"].append(it["_q"])
    return recs, order


def centroids(by_city):
    out = {}
    for label, items in by_city.items():
        lons = [r["lon"] for r in items if r.get("lon") is not None]
        lats = [r["lat"] for r in items if r.get("lat") is not None]
        if lons and lats:
            out[label] = (sum(lons) / len(lons), sum(lats) / len(lats))
    return out


def aliases(label):
    base = city_base(label).lower()
    return ALIAS.get(city_base(label), (base,))


def pick_city(rec, order, cent):
    """Город карточки: сначала по адресу (левее — главнее), потом по близости.

    None значит «город не наш»: карточка нашлась в чужой выдаче (например,
    душанбинский салон в поиске по Бохтару) — в региональный блок её не берём.
    """
    addr = (rec.get("fullAddress") or rec.get("address") or u"").lower()
    if any(w in addr for w in OFF_CITY):
        return None
    hits = []
    for label in order:
        for al in aliases(label):
            pos = addr.find(al)
            if pos >= 0:
                d = 0.0
                if label in cent and rec.get("coordinates"):
                    lon, lat = rec["coordinates"]
                    d = km(lon, lat, cent[label][0], cent[label][1])
                hits.append((pos, d, label))
                break
    if hits:
        hits.sort()
        return hits[0][2]
    if not rec.get("coordinates") or not cent:
        return rec["_cities"][0] if rec.get("_cities") else None
    lon, lat = rec["coordinates"]
    near = sorted(((km(lon, lat, c[0], c[1]), label)
                   for label, c in cent.items()))
    if near and near[0][0] <= NEAR_KM:
        return near[0][1]
    # Адрес молчит — доверяем городу запроса, но только если он рядом.
    for label in rec.get("_cities") or []:
        if label in cent and km(lon, lat, cent[label][0], cent[label][1]) <= MAX_KM:
            return label
    return None


def clean_addr(rec, label):
    addr = rec.get("address") or u""
    keep = []
    for part in [p.strip() for p in addr.split(u",")]:
        low = part.lower()
        if not part or any(w in low for w in REGION_WORDS):
            continue
        if low in aliases(label):
            continue
        keep.append(part)
    return u", ".join(keep)


def operator_of(rec):
    # Слаг карточки (``o_mobile``, ``zet_mobile_tsentr_obsluzhivaniya``) — самый
    # надёжный признак марки: в названиях её пишут и кириллицей, и латиницей,
    # порой в одном слове («O-Мobile»).
    text = u" ".join([rec.get("title") or u"",
                      (rec.get("seoname") or u"").replace(u"_", u" ")] + [
        c.get("name") or u"" for c in (rec.get("categories") or [])]).lower()
    for op, rx in BRAND_RE:
        if rx.search(text):
            return op
    return u"Прочие салоны"


def site_of(rec):
    """Свой сайт организации (ссылки на Яндекс и соцсети не в счёт)."""
    for u in rec.get("urls") or []:
        s = u.get("url") if isinstance(u, dict) else u
        if not s or "yandex" in s or "2gis" in s:
            continue
        if s.startswith("http"):
            return s
    return None


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


def phone_of(rec):
    out = []
    for p in rec.get("phones") or []:
        num = p.get("number") or p.get("value")
        if num and num not in out:
            out.append(num)
    return out


def nearest_osm(rec, rows):
    """(точка OSM, расстояние в км) — ближайшая к карточке, если она рядом."""
    if not rec.get("coordinates"):
        return None, 1e9
    lon, lat = rec["coordinates"]
    best, dist = None, OSM_MATCH_M / 1000.0
    for r in rows:
        if r.get("lon") is None or r.get("lat") is None:
            continue
        d = km(lon, lat, r["lon"], r["lat"])
        if d < dist:
            best, dist = r, d
    return best, dist


def row_of(rec, osm, oskm, label):
    title = rec.get("title") or u"?"
    if rec.get("coordinates"):
        lon, lat = rec["coordinates"]
        coords = u"%.6f, %.6f" % (lat, lon)
    else:
        coords = u"—"
    parts = [u"- **%s**" % title, u"· %s" % coords,
             u"· [Яндекс](%s)" % card_url(rec)]
    # Ссылку на OSM даём только в том же доме (25 м): в 80 м у блошиного рынка
    # ближайшей точкой оказывается соседняя лавка — это уже misinformation.
    if osm and oskm <= OSM_LINK_KM:
        parts.append(u"· [OSM](%s)" % osm["osm_url"])
    site = site_of(rec)
    if site:
        parts.append(u"· [сайт](%s)" % site)
    phones = phone_of(rec)
    if not phones and osm and osm.get("phone"):
        phones = [osm["phone"]]
    if phones:
        parts.append(u"· тел. %s" % u", ".join(phones[:2]))
    rating = rec.get("ratingData") or {}
    if rating.get("ratingCount", 0) >= 3 and rating.get("ratingValue"):
        parts.append(u"· ★ %.1f (%d)" % (rating["ratingValue"],
                                         rating["ratingCount"]))
    addr = clean_addr(rec, label)
    if not addr and osm and osm.get("addr_street"):
        addr = osm["addr_street"]
    if addr:
        parts.append(u"· _(%s)_" % addr)
    return u" ".join(parts)


def row_osm_only(r, label):
    parts = [u"- **%s**" % (r.get("name") or u"?"),
             u"· %.6f, %.6f" % (r["lat"], r["lon"]),
             u"· [OSM](%s)" % r["osm_url"],
             u"· [Яндекс-поиск](%s)" % search_url(u"%s %s" % (
                 r.get("name") or u"", city_base(label)))]
    note = []
    if r.get("addr_street"):
        note.append(r["addr_street"])
    elif r.get("phone"):
        note.append(u"тел. %s" % r["phone"])
    if label == NO_POINT_CITY:
        note.append(NO_POINT_CITY.lower())
    if note:
        parts.append(u"· _(%s)_" % u"; ".join(note))
    return u" ".join(parts)


def render():
    order, by_city, rows = load_osm()
    cent = centroids(by_city)
    recs, rec_order = load_cards()
    if not recs:
        raise SystemExit("no cards in cards.jsonl — run --collect first")

    # дубли карточек в одной точке (у Яндекса их бывает по два) — режем
    seen, cities = set(), {}
    matched = set()
    dropped = 0
    for iid in rec_order:
        rec = recs[iid]
        label = pick_city(rec, order, cent)
        if label is None:
            dropped += 1
            continue
        osm, oskm = nearest_osm(rec, rows)
        if osm:
            matched.add(id(osm))
        key = ((rec.get("title") or u"").lower(),
               tuple(round(v, 5) for v in (rec.get("coordinates") or [0, 0])))
        if key in seen:
            continue
        seen.add(key)
        cities.setdefault(label, []).append((rec, osm, oskm))

    # На одну точку OSM в одном доме приходится по две-три карточки (Tcell и
    # МегаФон в одном здании): ссылку на неё отдаём только ближайшей, иначе
    # читатель решит, что это один и тот же салон.
    claims = {}
    for items in cities.values():
        for i, (rec, osm, oskm) in enumerate(items):
            if osm:
                claims.setdefault(id(osm), []).append((oskm, items, i))
    for group in claims.values():
        if len(group) < 2:
            continue
        group.sort()
        for _d, items, i in group[1:]:
            rec, _o, _k = items[i]
            items[i] = (rec, None, 1e9)

    lines = [u"### Салоны связи — регионы Таджикистана (Яндекс.Карты)", u""]
    ncards = sum(len(v) for v in cities.values())
    phones = sum(1 for v in cities.values() for r, o, _ in v
                 if phone_of(r) or (o and o.get("phone")))
    sites = sum(1 for v in cities.values() for r, o, _ in v if site_of(r))
    rated = sum(1 for v in cities.values() for r, o, _ in v
                if (r.get("ratingData") or {}).get("ratingCount", 0) >= 3)
    lines.append(
        u"_Источник: Яндекс.Карты, съём %s. Запросы вида «Tcell Бохтар» "
        u"разобраны до карточек: название, координаты, ссылка на карточку, "
        u"адрес, телефон. Всего **%d** %s в **%d** %s; телефон — у %d, "
        u"сайт — у %d, рейтинг — у %d. Где карточка совпала с проверенной "
        u"точкой OSM (в пределах дома), рядом стоит ссылка на неё; точки, "
        u"которых в Яндексе нет, собраны в конце под катом._"
        % (time.strftime("%Y-%m-%d"), ncards,
           plural(ncards, u"салон", u"салона", u"салонов"), len(cities),
           plural(len(cities), u"городе", u"городах", u"городах"),
           phones, sites, rated))
    lines.append(u"")

    shown = 0
    for label in order:
        items = cities.get(label) or []
        if not items:
            continue
        by_op = {}
        for rec, osm, oskm in items:
            by_op.setdefault(operator_of(rec), []).append((rec, osm, oskm))
        lines.append(u"**%s** — %d %s" % (
            label, len(items),
            plural(len(items), u"салон", u"салона", u"салонов")))
        lines.append(u"")
        ops = [o for o in OP_ORDER if o in by_op] + \
              [o for o in by_op if o not in OP_ORDER]
        for op in ops:
            arr = by_op[op]
            arr.sort(key=lambda t: ((t[0].get("title") or u"").lower(),
                                    t[0].get("address") or u""))
            lines.append(u"_**%s** (%d)_" % (op, len(arr)))
            for rec, osm, oskm in arr:
                lines.append(row_of(rec, osm, oskm, label))
            lines.append(u"")
        lines.append(u"")
        shown += len(items)

    left = [r for r in rows if id(r) not in matched]
    if left:
        left.sort(key=lambda r: (r["city"], r.get("name") or u""))
        lines.append(u"<details><summary>Точки, которых нет в карточках "
                     u"Яндекса — %d (только OSM)</summary>" % len(left))
        lines.append(u"")
        cur = None
        for r in left:
            if r["city"] != cur:
                cur = r["city"]
                lines.append(u"")
                lines.append(u"**%s**" % cur)
                lines.append(u"")
            lines.append(row_osm_only(r, cur))
        lines.append(u"")
        lines.append(u"</details>")
        lines.append(u"")

    text = u"\n".join(lines).rstrip() + u"\n"
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(text)
    print("block: %d cards, %d cities, %d osm-only, %d off-city -> %s (%d bytes)"
          % (shown, len(cities), len(left), dropped, os.path.basename(OUT),
             len(text)))
    return text


def splice(text):
    body = io.open(DST, encoding="utf-8").read()
    for b, e in ((BEGIN, END), (OLD_BEGIN, OLD_END)):
        i, j = body.find(b), body.find(e)
        while i >= 0 and j > i:
            body = body[:i] + body[j + len(e):]
            i, j = body.find(b), body.find(e)
    anchor = u"<!-- TELECOM_BLOCK_END -->"
    if anchor not in body:
        raise SystemExit("anchor not found: TELECOM_BLOCK_END")
    wrapped = u"\n\n%s\n\n%s\n%s" % (BEGIN, text.strip(), END)
    body = body.replace(anchor, anchor + wrapped, 1)
    body = body.replace(u"\n\n\n\n", u"\n\n\n")
    io.open(DST, "w", encoding="utf-8", newline="\n").write(body)
    print("spliced into build/45_svyaz.md (%d bytes)" % len(body))


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
    splice(render())
    if "--build" in args:
        import subprocess
        subprocess.call([sys.executable, "build.py"], cwd=WORK)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
