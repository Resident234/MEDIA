# -*- coding: utf-8 -*-
"""Что лежит в data.search / data.filters состояния выдачи: полный список id?

usage: python probe_state_deep.py

Извлечение карточек из состояния работает (gis_state.py), но в HTML только 12
карточек при `total` 1084. Проверяем, нельзя ли взять больше из того же
ответа:

1. `data.search` — часто там лежит `item_ids` со всеми id совпадений (карты
   же надо чем-то рисовать!), даже если самих карточек в выдаче 12;
2. `data.filters` — доступные фасеты (районы, «круглосуточные», рубрики):
   если фильтр меняет выдачу, полный список собирается обходом фасетов;
3. `data.rubric`/`data.rubricator` — id рубрик, чтобы ходить по поддерубрикам;
4. любые длинные массивы чисел/строк-id в состоянии.

Ответ ASCII-escaped, сводка в _state_deep.json.
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gis_state                                            # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def walk(node, path, out, depth=0):
    """Собрать пути к списочным узлам и их размеры."""
    if depth > 7:
        return
    if isinstance(node, list):
        if node:
            kinds = set(type(x).__name__ for x in node[:5])
            out.append((path, len(node), sorted(kinds)))
        for x in node[:3]:
            walk(x, path + "[]", out, depth + 1)
    elif isinstance(node, dict):
        for k, v in node.items():
            walk(v, path + "." + k, out, depth + 1)


def main():
    body = gis_state.fetch(gis_state.search_url("dushanbe", "аптеки"))[1]
    if not body:
        sys.exit("fetch failed")
    st = gis_state.state_of(body)
    print("state:", bool(st), "total:", gis_state.total_of(st))
    data = st.get("data") or {}
    out = {"top_data_keys": sorted(data.keys())}
    srch = data.get("search") or {}
    print("search keys:", ascii_(sorted(srch.keys())[:40]))
    for k, v in sorted(srch.items()):
        if isinstance(v, list):
            print("  search.%-24s list len=%d kinds=%s" % (
                k, len(v), ascii_(sorted(set(type(x).__name__ for x in v[:3])))))
        elif isinstance(v, dict):
            print("  search.%-24s dict keys=%s" % (k, ascii_(sorted(v.keys())[:12])))
        else:
            print("  search.%-24s %s" % (k, ascii_(str(v)[:70])))
    lists = []
    walk(st, "", lists)
    big = sorted([x for x in lists if x[1] >= 5], key=lambda x: -x[1])[:40]
    print("=== big list nodes ===")
    for p, n, k in big:
        print("  %-70s %5d %s" % (ascii_(p)[:70], n, k))
    out["big_lists"] = [[ascii_(p), n, k] for p, n, k in big]
    flt = data.get("filters") or {}
    print("=== filters ===")
    print("filters keys:", ascii_(sorted(flt.keys())[:20]))
    txt = json.dumps(flt, ensure_ascii=False)
    print("filters size:", len(txt))
    # какие значения фильтров видны (районы, круглосуточно)
    names = re.findall(r'"(?:name|title)":"([^"]{2,40})"', txt)
    out["filter_names"] = sorted(set(names))[:60]
    print("filter names:", ascii_(json.dumps(out["filter_names"], ensure_ascii=True))[:1500])
    rub = data.get("rubric")
    out["rubric"] = ascii_(json.dumps(rub, ensure_ascii=True)[:1200]) if rub else None
    print("rubric:", out["rubric"][:800] if out["rubric"] else None)
    io.open(os.path.join(HERE, "_state_deep.json"), "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=True, indent=1)[:400000])
    io.open(os.path.join(HERE, "_probe_dushanbe_apteki.html"), "w",
            encoding="utf-8").write(body)


if __name__ == "__main__":
    main()
