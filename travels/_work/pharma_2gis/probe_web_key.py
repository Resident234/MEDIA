# -*- coding: utf-8 -*-
"""Проверить ключ веб-клиента 2ГИС из конфига страницы: пагинация и лимиты.

usage: python probe_web_key.py

`__customcfg` на 2gis.tj содержит `webApiKey` — тот самый ключ, с которым
веб-приложение ходит в `catalog.api.2gis.ru`. Наш демо-ключ заблокирован, но
ключ вебклиента это не затрагивает. Если он живой, 2GIS-часть раздела 11
делается тем же отработанным каналом, что и раздел 8: рубрика «Аптеки» (id
207), страницы и, если понадобится, рекурсия по плиткам.

Замеряем ровно то, что нужно для планирования объёма:
1. отвечает ли ключ вообще (items по Душанбе, рубрика 207);
2. какой `limit` пропускает сервер (12, 50, 100 — у веба потолок другой, чем
   у демо-ключа 5×10);
3. работает ли `page=N` (иначе список берётся плитками);
4. сколько всего аптек по Душанбе и по остальным городам Таджикистана (у 2ГИС
   каталог страны ограничен Душанбе — проверяем ещё раз на аптеках, чтобы
   утверждение в разделе опиралось на данные, а не на память);
5. видны ли в ответе часы работы (`schedule`) — тогда отдельный обход
   карточек ради графика не нужен.

Ключ в отчёты не печатается.
"""
import io
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gis_state                                            # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DUSHANBE = "70030076174471798"
PHARM_RUBRIC = "207"


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def web_key():
    body = gis_state.fetch(gis_state.search_url("dushanbe", "аптека"))[1]
    if not body:
        return None
    i = body.find("var __customcfg = JSON.parse(")
    if i < 0:
        return None
    lit, _ = gis_state._js_string(body, body.index("'", i + 28))
    try:
        cfg = json.loads(lit)
    except ValueError:
        return None
    return cfg.get("webApiKey"), cfg.get("webApi3Url"), cfg.get("webApiUrl")


def api(url):
    code, body = gis_state.fetch_any(url)
    if not body:
        return None, code
    try:
        return json.loads(body), None
    except ValueError:
        return None, "not json: " + ascii_(body[:200])


def main():
    got = web_key()
    if not got:
        sys.exit("no web key in cfg")
    key, api3, api2 = got
    print("web key found:", bool(key), "api3:", api3)
    out = {"api3": api3, "api2": api2}
    base = (api3 or "https://catalog.api.2gis.ru/3.0/") + "items"

    def call(**kw):
        kw.setdefault("key", key)
        return api(base + "?" + urllib.parse.urlencode(kw))

    print("=== rubric 207, dushanbe ===")
    j, err = call(q="аптеки", city_id=DUSHANBE, rubric_id=PHARM_RUBRIC, limit=12)
    if not j:
        print("FAIL", ascii_(err))
        out["first"] = {"fail": ascii_(err or "no json")[:400]}
        io.open(os.path.join(HERE, "_web_key_probe.json"), "w",
                encoding="utf-8").write(json.dumps(out, ensure_ascii=True, indent=1))
        sys.exit("key dead")
    res = j.get("result") or {}
    total = res.get("total")
    items = res.get("items") or []
    print("total:", total, "items:", len(items))
    first = items[0] if items else {}
    print("fields of item:", ascii_(sorted(first.keys()))[:600])
    frag = json.dumps(first, ensure_ascii=True)
    out["first_item_fields"] = sorted(first.keys())
    out["has_schedule_in_items"] = bool(re.search(r'"schedule"|"working_hours"', frag))
    out["has_rubrics"] = bool(re.search(r'"rubrics"', frag))
    out["has_rating"] = bool(re.search(r'"rating"', frag))
    out["total_rubric_dushanbe"] = total
    print("schedule in items:", out["has_schedule_in_items"],
          "rubrics:", out["has_rubrics"], "rating:", out["has_rating"])

    print("=== limits ===")
    lim = {}
    for want in (12, 50, 100, 200):
        j2, _ = call(q="аптеки", city_id=DUSHANBE, rubric_id=PHARM_RUBRIC, limit=want)
        got_n = len(((j2 or {}).get("result") or {}).get("items") or [])
        lim[want] = got_n
        print("  requested", want, "->", got_n)
        time.sleep(1.2)
    out["limits"] = lim

    print("=== pages ===")
    pg = {}
    maxlim = max([k for k, v in lim.items() if v] or [12])
    for page in (1, 2, 3):
        j3, _ = call(q="аптеки", city_id=DUSHANBE, rubric_id=PHARM_RUBRIC,
                     limit=maxlim, page=page)
        its = ((j3 or {}).get("result") or {}).get("items") or []
        ids = [i.get("id") for i in its]
        pg[page] = {"n": len(ids), "head": ids[:3]}
        print("  page", page, "->", len(ids), ascii_(ids[:3]))
        time.sleep(1.2)
    same = pg.get(1, {}).get("head") == pg.get(2, {}).get("head")
    out["pages"] = pg
    out["pages_work"] = not same
    print("  pagination works:", not same)

    print("=== other cities of Tajikistan ===")
    cities = {}
    for name, q in [("khujand", "Худжанд"), ("bohtar", "Бохтар"), ("kulob", "Куляб"),
                    ("regar", "Вахдат"), ("nurek", "Нурек"), ("horog", "Хорог"),
                    ("konibodom", "Конибодом"), ("tursunzoda", "Турсунзаде"),
                    ("pendjikent", "Пенджикент"), ("isfara", "Исфара")]:
        j4, _ = call(q=q + " аптека", limit=10)
        rs = ((j4 or {}).get("result") or {}).get("items") or []
        seen = {}
        for it in rs:
            c = (it.get("city_name") or (it.get("address") or {}).get("city_name")
                 or it.get("adm_div_name"))
            if c:
                seen[c] = seen.get(c, 0) + 1
        cities[name] = {"total": (j4 or {}).get("result", {}).get("total"),
                        "cities_in_items": seen}
        print("  %-11s total=%s %s" % (name, cities[name]["total"],
                                       ascii_(json.dumps(seen, ensure_ascii=True))[:120]))
        time.sleep(1.2)
    out["other_cities"] = cities
    io.open(os.path.join(HERE, "_web_key_probe.json"), "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=True, indent=1))
    print("saved _web_key_probe.json")


if __name__ == "__main__":
    main()
