# -*- coding: utf-8 -*-
"""Какие параметры и SEO-пути SSR-выдачи 2ГИС меняют набор из 12 карточек.

usage: python probe_facets.py

API 2ГИС закрыт для обоих ключей (демо-ключ и `webApiKey` из конфига страницы
отдают `403 apiKeyIsBlocked`), браузер — капча. Живой канал один: серверная
выдача `2gis.tj/<город>/search/<запрос>`, где лежит ровно 12 карточек из
`total` (1084 по «аптеки», `pages: 91`). Полный список Душанбе можно собрать
только шириной: каждый вариант запроса/фильтра отдаёт свои 12, и если варианты
непересекающиеся, объединение накрыто за десятки обращений.

Скрипт сначала вытаскивает из состояния страницы сами доступные фасеты
(районы, поддерубрики, значения фильтров), затем дёргает варианты и считает
прирост уникальных id:

1. сортировки (`sorting=by_rating|by_name|opened_time`) — часто это другой
   срез тех же 12;
2. рубрики/подрубрики из блока фильтров (`207 Аптеки`, `208 БАДы`, `660`…);
3. районы города (`district=<id>`);
4. SEO-пути рубрик (`/rubric/<alias>`, `/rubrics/…`, `/type/…`) — у 2ГИС
   SEO-списки умеют пагинацию в URL, в отличие от поисковой выдачи;
5. разные тексты запроса (сети/вывески, таджикские слова, «аптека 24 часа»).

По итогу — честная цифра: сколько уникальных id дают N запросов, чтобы понять,
какую долю от 1084 закрывает 2GIS-канал.
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
CITY = "dushanbe"
BASE_Q = "аптеки"


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def get_items(url):
    """(ids, total, ok) — разбор SSR-выдачи по URL."""
    code, body = gis_state.fetch(url)
    if not body:
        return set(), None, code
    st = gis_state.state_of(body)
    if not st:
        return set(), None, "no state"
    return (set(i for i, _ in gis_state.items_of(st)),
            gis_state.total_of(st), "ok")


def facets(state):
    """Доступные фасеты: районы, подрубрики, значения фильтров."""
    data = state.get("data") or {}
    flt = data.get("filters") or {}
    key = list(flt)[0] if flt else None
    node = flt.get(key, {}) if key else {}
    out = {"rubrics": [], "districts": [], "widget_values": [], "sorts": []}
    inner = node.get("filters") or {}
    for r in inner.get("rubrics") or []:
        out["rubrics"].append({"id": r.get("id"), "name": r.get("name"),
                               "count": r.get("count")})
    spatial = inner.get("spatial") or {}
    for d in (spatial.get("districts") or [])[:20]:
        out["districts"].append({"id": d.get("id"), "name": d.get("name"),
                                 "count": d.get("count")})
    for w in (node.get("widgets") or {}).values():
        for grp in w if isinstance(w, list) else []:
            for it in (grp.get("items") or []):
                for x in it if isinstance(it, list) else [it]:
                    if isinstance(x, dict) and x.get("values"):
                        out["widget_values"].append({
                            "text": x.get("text"), "type": x.get("type"),
                            "value_type": x.get("value_type"), "values": x.get("values")})
    for a in inner.get("attributes") or []:
        if a.get("type") == "sort":
            out["sorts"].append(a.get("tag"))
    return out


def main():
    url0 = gis_state.search_url(CITY, BASE_Q)
    code, body = gis_state.fetch(url0)
    if not body:
        sys.exit("base fetch failed: " + ascii_(code))
    st = gis_state.state_of(body)
    f = facets(st)
    print("facets:", ascii_(json.dumps({k: v[:9] for k, v in f.items()},
                                       ensure_ascii=True))[:2500])
    io.open(os.path.join(HERE, "_facets.json"), "w", encoding="utf-8").write(
        json.dumps(f, ensure_ascii=False, indent=1))

    variants = []
    for s in (f["sorts"] or ["by_rating", "by_name", "opened_time"]):
        variants.append(("sort_" + s, url0 + "?sorting=" + s))
    for r in f["rubrics"][:6]:
        variants.append(("rubric_" + str(r["id"]),
                         url0 + "?rubric_id=" + str(r["id"])))
    for d in f["districts"][:10]:
        variants.append(("district_" + str(d["id"]),
                         url0 + "?district=" + urllib.parse.quote(
                             str(d["id"]).encode("utf-8"))))
        variants.append(("q_district_" + str(d["id"]),
                         gis_state.search_url(CITY, "аптека " + str(d.get("name") or ""))))
    for w in f["widget_values"][:6]:
        v = (w.get("values") or [None])[0]
        if v:
            variants.append(("widget_" + str(v), url0 + "?" + str(v) + "=1"))
    extra_queries = ["аптека 24 часа", "круглосуточная аптека", "аптечный пункт",
                     "дорухона", "фармация", "аптека рядом", "лекарства",
                     "аптека Исмоили Сомони", "аптека Фирдоуси", "аптека Сино"]
    for i, q in enumerate(extra_queries):
        variants.append(("q%02d_%s" % (i, ascii_(q)[:14]), gis_state.search_url(CITY, q)))
    seo = [
        ("seo_rubric_alias", "https://2gis.tj/%s/rubric/apteki" % CITY),
        ("seo_rubrics_alias", "https://2gis.tj/%s/rubrics/apteki" % CITY),
        ("seo_type_apteki", "https://2gis.tj/%s/type/apteki" % CITY),
        ("seo_rubric_id", "https://2gis.tj/%s/rubric/207" % CITY),
        ("seo_search_alias", "https://2gis.tj/%s/search/apteki" % CITY),
        ("seo_apteki_page2", "https://2gis.tj/%s/search/apteki?page=2" % CITY),
    ]
    union, rows = set(), {}
    print("=== variants ===")
    for name, url in variants + seo:
        ids, total, ok = get_items(url)
        grow = len(ids - union)
        union |= ids
        rows[name] = {"url": url, "ok": ok, "ids": len(ids), "new": grow, "total": total}
        print("%-24s ok=%-9s ids=%2d new=%2d union=%3d total=%s" % (
            name, ok, len(ids), grow, len(union), total))
        time.sleep(1.0)
    print("UNION:", len(union), "из 1084")
    io.open(os.path.join(HERE, "_facet_probe.json"), "w", encoding="utf-8").write(
        json.dumps({"facets": f, "variants": rows, "union": sorted(union),
                    "union_size": len(union)}, ensure_ascii=True, indent=1))


if __name__ == "__main__":
    main()
