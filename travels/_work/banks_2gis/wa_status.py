# -*- coding: utf-8 -*-
"""Какие сети банков УЖЕ имеют WhatsApp в banks_2gis/card.jsonl.

Сравнивает с полным списком 15 сетей из org_names и говорит:
- сеть закрыта (есть хотя бы один wa.me в card.jsonl)
- сеть не закрыта (нужен Yandex-browser или телефонный обход)
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CARDS = os.path.join(HERE, "card.jsonl")
ROWS = os.path.join(HERE, "rows.jsonl")

sys.path.insert(0, HERE)
from make_md import network_of  # noqa: E402


def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def main():
    # card_id -> rec
    cards = {}
    for l in io.open(CARDS, encoding="utf-8"):
        try:
            r = json.loads(l)
            cards[r.get("id")] = r
        except ValueError:
            pass
    nets_all = {}
    nets_wa = {}
    for l in io.open(ROWS, encoding="utf-8"):
        r = json.loads(l)
        if not r.get("is_bank"):
            continue
        n = network_of(r)
        nets_all[n] = nets_all.get(n, 0) + 1
        c = cards.get(r.get("id")) or {}
        if c.get("whatsapp_url"):
            nets_wa.setdefault(n, []).append((r.get("name"), c.get("whatsapp_url")))
    print("== Networks covered by WhatsApp already ==")
    for n, lst in sorted(nets_wa.items(), key=lambda kv: -len(kv[1])):
        print("%s: %d/%d branches have WA" % (a(n), len(lst), nets_all[n]))
        for name, url in lst[:3]:
            print("   ", a(name), url)
    print()
    print("== Networks WITHOUT WhatsApp ==")
    for n in sorted(nets_all, key=lambda k: -nets_all[k]):
        if n in nets_wa:
            continue
        print("   %s  branches=%d" % (a(n), nets_all[n]))


if __name__ == "__main__":
    main()
