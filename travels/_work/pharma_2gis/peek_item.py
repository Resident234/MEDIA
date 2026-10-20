# -*- coding: utf-8 -*-
"""Что лежит внутри одной карточки выдачи SSR-поиска.

usage: python peek_item.py

Нужно понять, сняты ли в выдаче сразу `working_hours`/`contacts`/`website`/
`apps`, или только короткое превью (часы+адрес) и карточку придётся докачивать
отдельным запросом `/dushanbe/firm/<id>/`.
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
print("items:", len(items))
if items:
    i0, d0 = items[0]
    print("id:", i0)
    print("keys:", sorted(d0.keys()))
    print("schedule:", json.dumps(d0.get("schedule"), ensure_ascii=False)[:600])
    print("contacts:", json.dumps(d0.get("contacts"), ensure_ascii=False)[:400])
    print("urls:", json.dumps(d0.get("urls"), ensure_ascii=False)[:400])
    print("website:", json.dumps(d0.get("website"), ensure_ascii=False))
    print("attribute_groups:", json.dumps(d0.get("attribute_groups"),
                                          ensure_ascii=False)[:600])
    print("external_content:", json.dumps(d0.get("external_content"),
                                          ensure_ascii=False)[:400])
    print("categories:", json.dumps(d0.get("categories"), ensure_ascii=False))
