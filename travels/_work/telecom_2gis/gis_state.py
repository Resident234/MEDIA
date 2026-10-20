# -*- coding: utf-8 -*-
"""Извлечение состояния страницы из HTML выдачи 2ГИС (общий модуль).

usage: import gis_state; st = gis_state.state_of(html_text)

Сервер выдачи 2gis.tj кладёт состояние страницы в
`var initialState = JSON.parse('<JS-строка>')`, где кавычки экранированы.
Прямой raw_decode по маркеру `"items":[` поэтому не работает (первая
попытка — parse_ssr_search.py). Модуль умеет:

1. доставать JS-строковую литерал после `JSON.parse(`, уважая `\'` и `\\`,
   расэкранивать его и разбирать как JSON;
2. доставать карточки выдачи: `data.entity.profile.<id>.data` — там id,
   название, адрес, координаты, рубрики, `schedule` с working_hours,
   `org_rating`, число отзывов;
3. искать полный список id совпадений, если сервер отдаёт его отдельно
   (строки вида `item_ids`/`results`), — от этого зависит, нужно ли городить
   enumeration запросами по улицам;
4. отдавать total по запросу.

fetch() — тот же канал, что и в ssr_shops.py: голый User-Agent `Mozilla/5.0`
(полный Chrome UA даёт JS-оболочку, настоящий браузер без куки — капчу).
"""
import io
import json
import os
import re
import time

import requests

UA = "Mozilla/5.0"
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
           "Accept-Language": "ru-RU,ru;q=0.8"}
PARSE_RE = re.compile(r"JSON\.parse\(\s*['\"]")

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _js_string(body, i):
    """Прочитать строковый литерал, начинающийся с кавычки в позиции i."""
    quote = body[i]
    out = []
    j = i + 1
    while j < len(body):
        c = body[j]
        if c == "\\":
            nxt = body[j + 1] if j + 1 < len(body) else ""
            if nxt == "n":
                out.append("\n")
            elif nxt == "t":
                out.append("\t")
            elif nxt == "r":
                out.append("\r")
            elif nxt == "u":
                out.append(chr(int(body[j + 2:j + 6], 16)))
                j += 4
            else:
                out.append(nxt)
            j += 2
            continue
        if c == quote:
            return "".join(out), j + 1
        out.append(c)
        j += 1
    return None, None


def state_of(body):
    """Первый JSON.parse(...) с узнаваемым состоянием страницы, либо None."""
    pos = 0
    while True:
        m = PARSE_RE.search(body, pos)
        if not m:
            return None
        s, end = _js_string(body, m.end() - 1)
        pos = (end or m.end())
        if not s or len(s) < 2000:
            continue
        try:
            st = json.loads(s)
        except ValueError:
            continue
        if isinstance(st, dict) and ("data" in st or "bss" in st):
            return st
    return None


def items_of(state):
    """Карточки выдачи: (id, данные) в порядке списка результатов."""
    if not state:
        return []
    data = state.get("data") or {}
    ent = data.get("entity") or {}
    prof = ent.get("profile") or {}
    order = []
    for key in ("result", "items", "item_ids", "results"):
        node = data.get(key) or ent.get(key)
        if isinstance(node, list):
            for x in node:
                if isinstance(x, dict):
                    x = x.get("id")
                if x:
                    order.append(str(x))
        elif isinstance(node, dict):
            for k in ("ids", "items", "results"):
                if isinstance(node.get(k), list):
                    order.extend(str(i.get("id") if isinstance(i, dict) else i)
                                 for i in node[k] if i)
    ids = order or list(prof)
    out = []
    for i in ids:
        rec = prof.get(i)
        if isinstance(rec, dict):
            out.append((i, rec.get("data") or rec))
    return out


def total_of(state):
    """Сколько всего нашлось сервером (не то, что отдано в HTML)."""
    if not state:
        return None
    best = None
    stack = [state]
    seen = 0
    while stack and seen < 4000:
        node = stack.pop()
        seen += 1
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("total", "total_results", "found") and isinstance(v, int):
                    if best is None or v > best:
                        best = v
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(node, list):
            stack.extend(x for x in node if isinstance(x, (dict, list)))
    return best


def normalize(item_id, d):
    """Поля, нужные разделу 11: название, адрес, координаты, часы, рейтинг."""
    out = {"id": item_id, "name": d.get("name")}
    addr = d.get("address")
    if isinstance(addr, dict):
        out["address"] = addr.get("value") or ", ".join(
            c.get("street", "") + " " + c.get("number", "")
            for c in addr.get("components") or [] if isinstance(c, dict)).strip(", ")
    else:
        out["address"] = d.get("address_name")
    out["address_name"] = d.get("address_name")
    dist = [x.get("name") for x in d.get("adm_div") or []
            if isinstance(x, dict) and x.get("type") == "district"]
    out["district"] = dist[0] if dist else None
    point = d.get("point") or (d.get("geometry") or {}).get("point")
    if isinstance(point, dict):
        out["lon"], out["lat"] = point.get("lon"), point.get("lat")
    elif isinstance(point, (list, tuple)) and len(point) == 2:
        out["lon"], out["lat"] = point[0], point[1]
    rubs = [{"id": r.get("id"), "name": r.get("name"), "kind": r.get("kind")}
            for r in d.get("rubrics") or [] if isinstance(r, dict)]
    out["rubrics"] = rubs
    out["is_24x7"] = bool((d.get("schedule") or {}).get("is_24x7")) \
        if isinstance(d.get("schedule"), dict) else None
    out["org_rating"] = d.get("org_rating")
    out["review_count"] = d.get("org_review_count")
    wh = d.get("working_time_minutes") or d.get("working_time")
    if wh:
        out["working_time_raw"] = wh
    return out


def search_url(city, query):
    import urllib.parse
    return "https://2gis.tj/%s/search/%s" % (city, urllib.parse.quote(
        query.encode("utf-8")))


def fetch(url, tries=3, pause=2.0):
    """HTML страницы выдачи/карточки: годный ответ только большой и без капчи."""
    last = None
    for attempt in range(1, tries + 1):
        try:
            r = SESSION.get(url, timeout=(15, 90))
            body = r.text
            if r.status_code == 200 and len(body) > 200000 and "captcha" not in r.url:
                return "fresh", body
            last = "blocked(code=%d,len=%d,url=%s)" % (r.status_code, len(body), r.url)
        except requests.RequestException as e:
            last = "error(%s)" % type(e).__name__
        time.sleep(pause * attempt)
    return last, ""


def fetch_any(url, tries=3, pause=2.0, min_len=40):
    """Ответ API: JSON маленький, поэтому порога HTML тут быть не должно.

    fetch() отбрасывает всё короче 200 КБ — для карточек это верно, но ответы
    catalog.api всегда меньше, и на них fetch возвращает пустое тело.
    """
    last = None
    for attempt in range(1, tries + 1):
        try:
            r = SESSION.get(url, timeout=(15, 90))
            body = r.text
            if r.status_code == 200 and len(body) >= min_len:
                return "fresh", body
            last = "short(code=%d,len=%d)" % (r.status_code, len(body))
        except requests.RequestException as e:
            last = "error(%s)" % type(e).__name__
        time.sleep(pause * attempt)
    return last, ""


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    name = [f for f in sorted(os.listdir(here))
            if f.startswith("_probe_search_") and os.path.getsize(
                os.path.join(here, f)) > 1000][-1]
    body = io.open(os.path.join(here, name), encoding="utf-8").read()
    st = state_of(body)
    print("state parsed:", st is not None)
    if st:
        print("top keys:", json.dumps(sorted(st.keys()), ensure_ascii=True))
        print("data keys:", json.dumps(sorted((st.get("data") or {}).keys()),
                                       ensure_ascii=True)[:900])
        print("entity keys:", json.dumps(sorted(((st.get("data") or {}).get("entity") or {}).keys()),
                                         ensure_ascii=True))
        it = items_of(st)
        print("items:", len(it), "total:", total_of(st))
        if it:
            print("first:", json.dumps(normalize(it[0][0], it[0][1]),
                                       ensure_ascii=True)[:700])
