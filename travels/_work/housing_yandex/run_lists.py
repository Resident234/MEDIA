# -*- coding: utf-8 -*-
"""Перепись жилья Таджикистана на Яндекс.Картах: списки по населённым пунктам.

Первый запрос по населённому пункту идёт по карте вокруг его центра
(``?text=<запрос>&ll=<lon>,<lat>&z=13``) — Яндекс сам перенаправляет такой
запрос в каталог подходящего города, а если каталога нет, оставляет поиск
по видимой области. Из адреса после перенаправления запоминается префикс
``.../search/``: остальные запросы этого города идут уже прямо в каталог,
без лишнего перехода (это и быстрее, и меньше злит антибот).

Панель отдаёт только 25 объектов на страницу, но состояние страницы
содержит все 25 сразу, а остальное добирается параметром ``?page=N``
(см. yxd.harvest_state). Дополнительные формулировки нужны потому, что
разные названия категорий дают разные наборы объектов.

usage:
  python run_lists.py                  # все населённые пункты, до 3 кругов
  python run_lists.py --limit 3        # первые три пункта (проверка)
  python run_lists.py --only ishkoshim # один пункт (имя, слаг или подсказка)
  python run_lists.py --rounds 1       # без повторов

Сбор: lists/<slug>__<query>.jsonl
Лог:  lists/run.log, карта каталогов: _towns.json
"""
import io
import json
import os
import re
import sys
import time
import urllib.parse

import yxd
import yxhttp
from cities import CITIES, QUERIES
from merge import coords as coords_of, km

HERE = os.path.dirname(os.path.abspath(__file__))
LISTS = os.path.join(HERE, "lists")
LOG = os.path.join(LISTS, "run.log")
TOWNS = os.path.join(HERE, "_towns.json")

# Порог, ниже которого дополнительные формулировки не нужны. На HTTP-канале
# запрос стоит семь секунд, так что опрашиваем все формулировки везде: разные
# слова дают разные объекты, и «Апартаменты» находит то, чего нет в «Гостинице».
TAIL_MIN = 0
# Пауза между кругами, если что-то не собралось (секунды).
RETRY_PAUSE = 600
# Если круг не принёс ни одного нового объекта — держим паузу дольше.
EMPTY_PAUSE = 900
# Транспорт: http (по умолчанию, без браузера) или browser (запасной).
TRANS = os.environ.get("YX_TRANSPORT", "http").lower()


def harvest(url):
    """Один запрос выдачи тем или иным каналом."""
    if TRANS == "browser":
        return yxd.harvest_state(url, budget=80, pages=4, tries=1)
    # 10 страниц по 25 — потолок для самого крупного города (у Душанбе
    # «меҳмонхона» отдаёт 155 объектов); обход прекращается сам, как только
    # очередная страница не приносит новых id.
    return yxhttp.harvest(url, pages=10, pause=3)


# В первую очередь — города, где жилья заведомо много: сбор длинный, и если
# его придётся прервать, основная масса объектов уже лежит в файлах.
PRIORITY = [u"Душанбе", u"Худжанд", u"Бохтар", u"Куляб", u"Хорог",
            u"Истаравшан", u"Пенджикент", u"Турсунзаде", u"Вахдат", u"Гиссар"]


def log(msg):
    line = "[%s] %s\n" % (time.strftime("%H:%M:%S"), msg)
    sys.stdout.buffer.write(line.encode("ascii", "backslashreplace"))
    sys.stdout.buffer.flush()
    io.open(LOG, "a", encoding="utf-8").write(line)


def slug(name):
    """Транслит для имени файла: только латиница/цифры/дефис."""
    table = {
        u"а": "a", u"б": "b", u"в": "v", u"г": "g", u"д": "d", u"е": "e",
        u"ё": "e", u"ж": "zh", u"з": "z", u"и": "i", u"й": "y", u"к": "k",
        u"л": "l", u"м": "m", u"н": "n", u"о": "o", u"п": "p", u"р": "r",
        u"с": "s", u"т": "t", u"у": "u", u"ф": "f", u"х": "h", u"ц": "c",
        u"ч": "ch", u"ш": "sh", u"щ": "sch", u"ъ": "", u"ы": "y", u"ь": "",
        u"э": "e", u"ю": "yu", u"я": "ya", u" ": "-",
    }
    out = []
    for ch in name.lower():
        out.append(table.get(ch, ch if ch.isalnum() and ch.isascii() else ""))
    return re.sub(r"-+", "-", "".join(out)).strip("-") or "town"


def prefix_of(base):
    """``.../10318/dushanbe/search/query/`` -> ``.../10318/dushanbe/search/``."""
    if not base or "/search/" not in base:
        return None
    return base.split("/search/")[0] + "/search/"


def still_open(out, done):
    """Не закрыт ли запрос, у которого собрано меньше, чем totalResultCount.

    Пагинация обрывается на «нет новых id», а общее число объектов Яндекс
    сообщает отдельно. Расхождение больше трёх значит, что часть списка не
    влезла в отведённые страницы, и запрос надо переспросить — с более
    глубокой пагинацией.
    """
    if not os.path.exists(done):
        return True
    try:
        txt = io.open(done, encoding="utf-8").read()
    except (IOError, OSError):
        return True
    # end=1 — пагинация дошла до конца: остаток totalResultCount это чужие
    # категории, которые Яндекс считает, но не показывает в списке.
    if "end=1" in txt:
        return False
    m = re.search(r"n=(\d+)\s+total=(\d+)", txt)
    if not m:
        return False
    return int(m.group(2)) > int(m.group(1)) + 3


def median_km(items, town):
    """Медианное расстояние выдачи от центра пункта, км (None, если мало данных)."""
    lon0, lat0 = [float(x) for x in town["ll"].split(",")]
    ds = []
    for it in items:
        lon, lat = coords_of(it)
        if lon is not None:
            ds.append(km(lon, lat, lon0, lat0))
    if len(ds) < 5:
        return None
    ds.sort()
    return ds[len(ds) // 2]


def is_relay(items, town, med):
    """Город без своего каталога: Яндекс отдаёт отели соседнего центра.

    Признак дважды: выдача далеко от пункта И ни в одном адресе нет его
    названия. Для настоящего города хотя бы часть адресов — местные.
    Порог 12 км: отели настоящего города лежат в радиусе пятёрки километров,
    а Вахдат, например, отдаёт Душанбе с медианой 19 км.
    """
    if med is None or med < 12:
        return False
    stem = town["name"].lower().replace(u"ё", u"е")[:3]
    for it in items:
        addr = (it.get("address") or it.get("fullAddress") or "").lower()
        if stem in addr:
            return False
    return True


def load_json(path):
    if os.path.exists(path):
        try:
            return json.load(io.open(path, encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def save_json(path, data):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=1))
    os.replace(tmp, path)


def rows(only):
    out = []
    for name, hint, lon, lat, region in CITIES:
        key = slug(hint)
        if only and only not in (name, key, hint):
            continue
        out.append({"name": name, "key": key,
                    "ll": "%.4f,%.4f" % (lon, lat), "region": region})
    out.sort(key=lambda t: PRIORITY.index(t["name"])
             if t["name"] in PRIORITY else len(PRIORITY))
    return out


def load_items(path):
    got = []
    if os.path.exists(path):
        for line in io.open(path, encoding="utf-8"):
            try:
                got.append(json.loads(line))
            except ValueError:
                pass
    return got


def mark_relays(todo):
    """Отметить уже собранные города, которые только транслируют регион.

    Нужно после смены правил на ходу: иначе город, чей первый запрос уже
    собран, никогда не пройдёт проверку и продолжит жечь лимит остальными
    формулировками.
    """
    marked = 0
    for town in todo:
        relay = os.path.join(LISTS, "%s__town.relay" % town["key"])
        if os.path.exists(relay):
            continue
        first = os.path.join(LISTS, "%s__%s.jsonl" % (town["key"],
                                                      QUERIES[0][1]))
        items = load_items(first)
        if len(items) < 5:
            continue
        med = median_km(items, town)
        if is_relay(items, town, med):
            io.open(relay, "w", encoding="utf-8").write(
                u"median %.1f km, no local addresses\n" % med)
            log("%s %s relays the regional centre (median %d km)" % (
                "mark", town["key"], int(med)))
            marked += 1
    return marked


def pass_over(todo, prefixes, round_no):
    """One full pass; returns (items, still missing, global ban seen)."""
    grand, missing = 0, 0
    for town in todo:
        seen = set()
        relay = os.path.join(LISTS, "%s__town.relay" % town["key"])
        if os.path.exists(relay):
            continue
        for qi, (qtext, qname) in enumerate(QUERIES, 1):
            out = os.path.join(LISTS, "%s__%s.jsonl" % (town["key"], qname))
            done = out + ".ok"
            got = load_items(out)
            for it in got:
                seen.add(it.get("id") or it.get("title"))
            if not still_open(out, done):
                # Маркер ставится и на «ничего не нашлось»: файла может не быть,
                # а вопрос уже закрыт.
                continue
            if qi > 3 and len(seen) < TAIL_MIN:
                continue
            pre = prefix_of(prefixes.get(town["name"]))
            if pre:
                url = pre + urllib.parse.quote(qtext.encode("utf-8")) + "/"
            else:
                url = yxd.search_url(qtext, ll=town["ll"], z=13)
            t0 = time.time()
            kind, items, total, base, complete = "timeout", [], None, None, False
            for attempt in (1, 2):
                try:
                    kind, items, total, base, complete = harvest(url)
                except Exception as exc:  # noqa: BLE001 - один сбой не рвёт проход
                    log("%s/%s EXC %s" % (town["key"], qname,
                                          yxd.show(str(exc))[:160]))
                    missing += 1
                    time.sleep(15)
                    break
                if base and base != prefixes.get(town["name"]):
                    prefixes[town["name"]] = base
                    save_json(TOWNS, prefixes)
                if kind != "throttled":
                    break
                log("%s/%s throttled, cooling (%ds)" % (
                    town["key"], qname, int(time.time() - t0)))
                # Одиночную заглушку имеет смысл переждать. Если и второй
                # заход пустой — окно антибота закрыто, и любое дальнейшее
                # тыканье только продлевает его.
                if attempt == 1:
                    if TRANS != "browser":
                        time.sleep(90)
                        continue
                    if yxd.cool(60, 2):
                        continue
                log("window closed: round %d aborted" % round_no)
                return grand, missing, True
            if kind == "none":
                # «Ничего не нашлось» — окончательный ответ, а не сбой. Без
                # маркера такой город переспрашивался бы каждый круг и съедал
                # лимит антибота.
                io.open(done, "w", encoding="utf-8").write(u"none n=0\n")
                log("%s/%s -> none, marked done %ds" % (
                    town["key"], qname, int(time.time() - t0)))
                time.sleep(10)
                continue
            if kind in ("timeout", "throttled"):
                log("%s/%s -> %s, retry later %ds" % (
                    town["key"], qname, kind, int(time.time() - t0)))
                missing += 1
                time.sleep(10)
                continue
            merged = {}
            for it in got + items:
                merged[it.get("id") or it.get("title")] = it
            grew = len(merged) - len(got)
            tmp = out + ".tmp"
            with io.open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                for it in merged.values():
                    it["_src"] = town["name"]
                    it["_q"] = qname
                    fh.write(json.dumps(it, ensure_ascii=False) + "\n")
                    seen.add(it.get("id") or it.get("title"))
            os.replace(tmp, out)
            grand += len(merged)
            # Панель отдаёт до 25 на страницу, но нумерация дальше плывёт:
            # «конца списка» у крупного города не видно, зато новые id
            # кончаются. Прирост меньше трёх — дальше ходить незачем.
            if complete or grew < 3:
                io.open(done, "w", encoding="utf-8").write(
                    "%s n=%d total=%s grew=%d end=%d\n" % (
                        qname, len(merged), total, grew, int(complete)))
            else:
                missing += 1
            log("r%d %s/%s -> %s n=%d total=%s done=%s %ds" % (
                round_no, town["key"], qname, kind, len(merged), total,
                int(complete), int(time.time() - t0)))
            if qi == 1:
                med = median_km(merged.values(), town)
                if is_relay(merged.values(), town, med):
                    io.open(relay, "w", encoding="utf-8").write(
                        u"median %.1f km, no local addresses\n" % med)
                    io.open(done, "w", encoding="utf-8").write(
                        u"relay n=%d\n" % len(merged))
                    log("%s relays the regional centre (median %d km), "
                        "rest of queries skipped" % (town["key"], int(med)))
                    break
            # HTTP-канал держит темп в пару секунд на страницу; браузерный
            # душится сразу, ему нужен долгий шаг.
            time.sleep(4 if TRANS == "http" else 45)
    return grand, missing, False


def main():
    os.makedirs(LISTS, exist_ok=True)
    only, limit, rounds = None, 0, 3
    scan = False
    args, i = sys.argv[1:], 0
    while i < len(args):
        if args[i] == "--only" and i + 1 < len(args):
            only, i = args[i + 1], i + 2
        elif args[i] == "--limit" and i + 1 < len(args):
            limit, i = int(args[i + 1]), i + 2
        elif args[i] == "--rounds" and i + 1 < len(args):
            rounds, i = int(args[i + 1]), i + 2
        elif args[i] == "--mark-relay":
            scan, i = True, i + 1
        else:
            only, i = args[i], i + 1
    todo = rows(only)
    if limit:
        todo = todo[:limit]
    prefixes = load_json(TOWNS)
    log("towns=%d queries=%d transport=%s session=%s tail_min=%d rounds=%d" % (
        len(todo), len(QUERIES), TRANS, yxd.SESSION, TAIL_MIN, rounds))
    if scan:
        log("relay scan: marked %d" % mark_relays(todo))
        return
    total_items, missing, blocked_last = 0, 0, False
    for r in range(1, rounds + 1):
        grand, missing, blocked = pass_over(todo, prefixes, r)
        total_items += grand
        blocked_last = blocked
        log("round %d done: items=%d missing=%d%s" % (
            r, grand, missing, " BAN" if blocked else ""))
        # Порядок важен: при бане на первом же запросе круга missing остаётся
        # нулём, и раньше сбор объявлял себя законченным.
        if blocked:
            log("global ban: waiting %ds before round %d" % (EMPTY_PAUSE, r + 1))
            time.sleep(EMPTY_PAUSE)
            continue
        if not missing:
            break
        if r < rounds:
            # Пустой круг — это антибот, а не отсутствие данных: ждём шире,
            # чтобы не просиживать все круги впустую.
            pause = RETRY_PAUSE if grand else EMPTY_PAUSE
            log("sleep %ds before round %d%s" % (
                pause, r + 1, "" if grand else " (empty round)"))
            time.sleep(pause)
    if missing or blocked_last:
        # Ненулевой код — сигнал супервизору взять новый заход: работа есть.
        log("NOT DONE. items=%d missing=%d ban=%d" % (
            total_items, missing, int(blocked_last)))
        return 2
    log("DONE. items=%d" % total_items)
    return 0


if __name__ == "__main__":
    sys.exit(main())
