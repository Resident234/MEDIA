# -*- coding: utf-8 -*-
"""Быстро определить total и rubrics для 'банки' в Душанбе (через gis_state)."""
import io
import json
import sys
import gis_state

def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")

def probe(q):
    url = gis_state.search_url("dushanbe", q)
    status, body = gis_state.fetch(url, tries=3, pause=1.5)
    if status != "fresh":
        return {"err": status}
    st = gis_state.state_of(body)
    total = gis_state.total_of(st)
    items = gis_state.items_of(st)
    rubs = {}
    for iid, d in items:
        for r in d.get("rubrics") or []:
            n = r.get("name")
            if n:
                rubs[n] = rubs.get(n, 0) + 1
    top = sorted(rubs.items(), key=lambda x: -x[1])[:12]
    return {"total": total, "items": len(items), "top_rubrics": top}

for q in (u"банки", u"банк", u"обмен валют", u"банкомат", u"Амонатбанк",
          u"Алина Банк", u"Спаталинбанк", u"Мехргонбанк", u"Элтерсан"):
    print(a(q), "->", a(json.dumps(probe(q), ensure_ascii=True)))
