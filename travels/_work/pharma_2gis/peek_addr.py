# -*- coding: utf-8 -*-
"""Посмотреть, как реально выглядит адрес в items_all.json."""
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SHOPS = os.path.join(HERE, "..", "shops_2gis")


def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


data = json.load(io.open(os.path.join(SHOPS, "items_all.json"), encoding="utf-8"))
print("list len", len(data))
sample = data[0]
print("keys:", a(list(sample.keys())))
addr = sample.get("address")
print("addr type:", a(type(addr).__name__))
print("addr:", a(json.dumps(addr, ensure_ascii=False)[:600]))
print("addr_name:", a(sample.get("address_name")))
print("unified:", a((addr or {}).get("unified") if isinstance(addr, dict) else None))
# Сквозная статистика по всем: есть ли components
n = 0
for it in data[:20]:
    ad = it.get("address")
    print("-", a(json.dumps(ad, ensure_ascii=False)[:400]))
