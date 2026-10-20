# -*- coding: utf-8 -*-
"""Доглядеть поля links/org/rubrics — как собрать URL карточки и имя сети.

usage: peek_item2.py
"""
import io
import json
import os

import gis_state

HERE = os.path.dirname(os.path.abspath(__file__))
BODY = io.open(os.path.join(HERE, "_probe_dushanbe_apteki.html"),
               encoding="utf-8").read()
st = gis_state.state_of(BODY)
items = gis_state.items_of(st)
i0, d0 = items[0]
print("links:", json.dumps(d0.get("links"), ensure_ascii=False))
print("org:", json.dumps(d0.get("org"), ensure_ascii=False))
print("rubrics:", json.dumps(d0.get("rubrics"), ensure_ascii=False))
print("poi_category:", json.dumps(d0.get("poi_category"), ensure_ascii=False))
print("address:", json.dumps(d0.get("address"), ensure_ascii=False))
print("address_name:", d0.get("address_name"))
print("adm_div:", json.dumps(d0.get("adm_div"), ensure_ascii=False))
print("point:", json.dumps(d0.get("point"), ensure_ascii=False))
print("search_attributes:", json.dumps(d0.get("search_attributes"),
                                       ensure_ascii=False))
