# -*- coding: utf-8 -*-
"""HTTP-канал Яндекс.Карт: тот же state-view, но без браузера.

Страница Карт серверная — полный набор объектов лежит в
``<script class="state-view">`` внутри HTML. Браузер при частых запросах
получает заглушку «limited», а обычный GET с настольным User-Agent отдаёт
данные даже в те минуты, когда браузер уже закрыт. Кроме того, пагинация
``?page=N`` доходит до конца списка: у Худжанда HTTP отдал 44 объекта там,
где панель показала 23.

Публичный вход один — ``harvest(url, pages, pause)`` с тем же контрактом,
что у ``yxd.harvest_state``: (kind, items, total, base, complete),
где kind: list | none | org | throttled | timeout.
"""
import json
import re
import time
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}
RE_STATE = re.compile(r'<script[^>]*class="state-view"[^>]*>(.*?)</script>',
                      re.S)
NO_RESULTS = (u"ничего не нашлось", u"Ничего не нашлось")
STUBS = (u"limited", u"showcaptcha", u"SmartCaptcha")


def _get(url, timeout=40):
    """Return (body, final_url); body is None when the answer is a stub."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            final = resp.geturl()
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429, 503):
            return None, url
        raise
    stripped = body.strip()
    if stripped == "limited" or any(s in final for s in STUBS):
        return None, final
    return body, final


def _results(body):
    """The results block of the first stack frame, or None.

    У каталога города это ``results``, у общего поиска по карте
    (``?text=``) — ``response``; поля внутри одинаковые.
    """
    match = RE_STATE.search(body)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return None
    stack = data.get("stack") or []
    if not stack or not isinstance(stack[0], dict):
        return None
    frame = stack[0]
    return frame.get("results") or frame.get("response") or None


def harvest(url, pages=6, pause=3):
    """Collect one query page by page; same contract as yxd.harvest_state."""
    items, seen, total = [], set(), None
    # ?text=... сам содержит запрос: отрезать его можно только у каталога.
    base = url.split("?")[0]
    is_catalog = "/search/" in base
    # Префиксом каталога делятся только каталожные адреса: из общего поиска
    # такой префикс не построить, и запоминать его нельзя.
    perfix = base if is_catalog else None
    complete = False
    for page in range(1, pages + 1):
        if page == 1:
            target = url
        else:
            sep = "&" if "?" in url else "?"
            target = "%s%spage=%d" % (url, sep, page)
        body, final = _get(target)
        if body is None:
            return "throttled", items, total, perfix, False
        res = _results(body)
        if res is None:
            if "/maps/org/" in final:
                return "org", items, total, perfix, True
            if any(n in body for n in NO_RESULTS):
                return "none", items, total, perfix, True
            return "timeout", items, total, perfix, False
        total = res.get("totalResultCount") or total
        batch = res.get("items") or []
        fresh = 0
        for item in batch:
            key = item.get("id") or item.get("title")
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
            fresh += 1
        # Конец списка — страница без новых id (нумерация у Яндекса плывёт).
        if page > 1 and (not batch or not fresh):
            complete = True
            break
        if len(batch) < 25 and page > 1:
            complete = True
            break
        time.sleep(pause)
    return ("list" if items else "none"), items, total, perfix, complete
