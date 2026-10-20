# -*- coding: utf-8 -*-
"""Проверить прокси-пути веб-клиента 2ГИС: /_/... на самом домене.

usage: python probe_proxy_paths.py

В конфиге страницы `webApiUrl = catalog.api.2gis.ru/2.0/`, `webApi3Url =
.../3.0/` и есть флаг `enableProxy`. Если клиент ходит не в API-домен с
ключом, а на относительный путь своего же домена (`2gis.tj/_/...`), то ключ
вообще не нужен — сервер проксирует сам, и куки страницы достаточно. Тогда
пагинация (`page=2`) и плиточный обход становятся доступны, и 1084 аптеки
Душанбе снимаются за ~90 запросов.

Скрипт:
1. печатает из конфига всё, что похоже на ключ/проект/флаг прокси;
2. дёргает набор правдоподобных путей с параметрами `q`, `key`, `city_id`,
   `page`, `limit` — и на GET, и на POST;
3. параллельно пробует тот же `items` на API-домене 2.0 с `project`-параметром
   вместо ключа (у внутреннего API 2ГИС проект иногда задаётся строкой).

Всё ASCII-escaped.
"""
import io
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gis_state                                            # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
Q = "аптека"


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def cfg_of(body):
    i = body.find("var __customcfg = JSON.parse(")
    if i < 0:
        return {}
    lit, _ = gis_state._js_string(body, body.index("'", i + 28))
    try:
        return json.loads(lit)
    except ValueError:
        return {}


def show(name, url, method="GET", data=None):
    try:
        if method == "GET":
            code, body = gis_state.fetch(url)
        else:
            r = gis_state.SESSION.post(url, data=data, timeout=(15, 60))
            code, body = (r.status_code, r.text)
    except Exception as exc:                       # noqa: BLE001
        code, body = -1, repr(exc)[:120]
    head = ascii_(re.sub(r"\s+", " ", body[:150])) if body else ""
    ok = code == 200 and len(body) > 200
    items = len(set(re.findall(r'"id"\s*:\s*"(7000\d{12,})"', body))) if ok else 0
    print("%-34s code=%s len=%6d firmids=%d %s" % (name, code, len(body), items,
                                                   head[:110]))
    return {"code": code, "len": len(body), "firmids": items, "head": head[:200]}


def main():
    body = gis_state.fetch(gis_state.search_url("dushanbe", Q))[1]
    if not body:
        sys.exit("fetch failed")
    cfg = cfg_of(body)
    print("cfg size:", len(json.dumps(cfg)))
    interesting = {k: v for k, v in cfg.items()
                   if re.search(r"(?i)(key|proxy|project|token|api)", k) and
                   not isinstance(v, (dict, list))}
    print("key-ish cfg:", ascii_(json.dumps(interesting, ensure_ascii=True))[:1500])
    out = {"cfg": interesting}
    qs = urllib.parse.quote(Q.encode("utf-8"))
    city = "70030076174471798"
    print("=== get-like paths on 2gis.tj ===")
    paths = [
        ("proxy_items", "https://2gis.tj/_/items?q=%s&city_id=%s&limit=12" % (qs, city)),
        ("proxy_search", "https://2gis.tj/_/search?q=%s&city_id=%s" % (qs, city)),
        ("proxy_catalog_items", "https://2gis.tj/_/catalog/items?q=%s" % qs),
        ("proxy_items_path", "https://2gis.tj/_/catalog/2gis.items?q=%s" % qs),
        ("proxy_v2", "https://2gis.tj/_/2.0/items?q=%s" % qs),
        ("dushanbe_items", "https://2gis.tj/dushanbe/items?q=%s" % qs),
        ("api20_noproj", "https://catalog.api.2gis.ru/2.0/items?q=%s&city_id=%s&limit=12" % (qs, city)),
        ("api20_proj", "https://catalog.api.2gis.ru/2.0/items?q=%s&city_id=%s&project=online_tj&limit=12" % (qs, city)),
        ("api30_noproj", "https://catalog.api.2gis.ru/3.0/items?q=%s&city_id=%s&limit=12" % (qs, city)),
        ("api30_dgis", "https://catalog.api.2gis.ru/3.0/items?q=%s&city_id=%s&project=dublgis&limit=12" % (qs, city)),
        ("search_page_page2_hdr", "https://2gis.tj/dushanbe/search/%s?page=2" % qs),
    ]
    out["probes"] = {}
    for name, url in paths:
        out["probes"][name] = show(name, url)
    print("=== post формы ===")
    for name, url, data in [
            ("post_proxy_items", "https://2gis.tj/_/items",
             {"q": Q, "city_id": city, "limit": "12"}),
            ("post_proxy_search_json", "https://2gis.tj/_/search", None)]:
        try:
            if data is None:
                r = gis_state.SESSION.post(url, json={"q": Q, "city_id": city,
                                                      "limit": 12, "page": 2},
                                           timeout=(15, 60))
            else:
                r = gis_state.SESSION.post(url, data=data, timeout=(15, 60))
            print("%-34s code=%s len=%d %s" % (name, r.status_code, len(r.text),
                                               ascii_(re.sub(r"\s+", " ", r.text[:120]))))
            out["probes"][name] = {"code": r.status_code, "len": len(r.text)}
        except Exception as exc:                   # noqa: BLE001
            print("%-34s err %s" % (name, ascii_(repr(exc)[:110])))
    io.open(os.path.join(HERE, "_proxy_probe.json"), "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=True, indent=1)[:120000])


if __name__ == "__main__":
    main()
