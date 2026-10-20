# -*- coding: utf-8 -*-
"""Распаковать data.search.pagination и data.filters: чем меряется страница выдачи.

usage: python probe_pagination.py

В состоянии выдачи есть `data.search.pagination` с ключом поискового события и
`data.filters` со списочными фасетами (30 атрибутов, 13 рубрик). Если в
pagination есть `page`/`per_page`/`total` и сам список id по страницам, то
страницы перебираются параметром, который сервер понимает, а не тем `page=`,
который он проигнорировал. Фасеты показывают, какими срезами можно дробить
запрос («аптека» × район/атрибут), чтобы каждой выдачей накрывать не больше 12
карточек.
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gis_state                                            # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def main():
    path = os.path.join(HERE, "_probe_dushanbe_apteki.html")
    body = io.open(path, encoding="utf-8").read()
    st = gis_state.state_of(body)
    data = st["data"]
    evkey = list((data.get("search") or {}).get("pagination") or {})[0]
    print("search event key:", evkey)
    print("=== pagination ===")
    print(ascii_(json.dumps(data["search"]["pagination"], ensure_ascii=True)[:2500]))
    print("=== search.profile[ev] ===")
    print(ascii_(json.dumps(data["search"]["profile"][evkey], ensure_ascii=True)[:1200]))
    print("=== appContext ===")
    print(ascii_(json.dumps(st.get("appContext"), ensure_ascii=True)[:1500]))
    print("=== filters ===")
    fkey = list(data["filters"])[0]
    flt = data["filters"][fkey]
    print("filters keys:", ascii_(sorted(flt.keys())))
    for grp in ("filters", "widgets"):
        node = flt.get(grp)
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, list):
                    names = [ascii_(json.dumps(x, ensure_ascii=True))[:170] for x in v[:6]]
                    print("  %s.%s (%d):" % (grp, k, len(v)))
                    for n in names:
                        print("    ", n)
                elif isinstance(node, dict):
                    print("  %s.%s = %s" % (grp, k, ascii_(json.dumps(v, ensure_ascii=True))[:200]))
    print("=== статус/сессия ===")
    print("status:", ascii_(json.dumps(st.get("status"), ensure_ascii=True))[:300])
    print("session:", ascii_(json.dumps(st.get("session"), ensure_ascii=True))[:600])


if __name__ == "__main__":
    main()
