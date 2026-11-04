# -*- coding: utf-8 -*-
"""Собирает из _parcel_full.jsonl человекочитаемый блок карточек для 73_dostavka.md.

Каждая карточка попадает ровно в одну категорию (приоритет сверху вниз), чтобы
не было повторов. ПВЗ и постаматы группируются по бренду/оператору — их много
(121 и 57), и поштучный список читается плохо.

Выход: _parcel_block.md (UTF-8). Console — только ASCII-статусы.
"""
import io
import json
import os
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "_parcel_full.jsonl")
OUT = os.path.join(HERE, "_parcel_block.md")

POCHTA = u"Почта"
EXP = u"Экспресс-почта"
PVZ = u"Нуқтаҳои додани фармоишҳои интернетӣ"
POSTAMAT = u"Терминалҳои амонатӣ"
CARGO = (u"Интиқоли байналмилалии бор",
         u"Боркашонии автомобилии байнишаҳрӣ",
         u"Боркашонии роҳи оҳан",
         u"Нақлиёти боркашонии ҳавоӣ")


def brand(name):
    n = (name or u"").split(u",")[0].strip()
    return n or u"—"


def bkey(name):
    """Ключ бренда для склейки вариантов написания (Lak lak == Laklak)."""
    return brand(name).lower().replace(u" ", u"").replace(u"-", u"")


def place(r):
    """Подпись точки: адрес, иначе район, иначе заглушка."""
    if r.get("address"):
        return r["address"]
    if r.get("district"):
        return u"%s (район)" % r["district"]
    return u"карточка"


def line(r):
    return u"[%s — %s](%s)" % (brand(r["name"]), place(r), r["url"])


def main():
    recs = [json.loads(l) for l in io.open(SRC, encoding="utf-8") if l.strip()]
    cats = collections.OrderedDict([
        ("pochta", []), ("exp", []), ("cargo", []),
        ("pvz", []), ("postamat", []),
    ])
    for r in recs:
        ir = set(r["in_rubrics"])
        if POCHTA in ir:
            cats["pochta"].append(r)
        elif EXP in ir:
            cats["exp"].append(r)
        elif PVZ in ir:
            cats["pvz"].append(r)
        elif POSTAMAT in ir:
            cats["postamat"].append(r)
        elif any(c in ir for c in CARGO):
            cats["cargo"].append(r)

    o = []
    w = o.append

    def simple(key, title):
        lst = sorted(cats[key], key=lambda r: (brand(r["name"]),
                                               r.get("address") or u""))
        w(u"**%s (%d)**" % (title, len(lst)))
        w(u"")
        for r in lst:
            w(u"- " + line(r))
        w(u"")

    simple("pochta", u"Почтовые отделения (`Почтаи Тоҷикистон`)")
    simple("exp", u"Экспресс-почта и курьерские службы")
    simple("cargo", u"Грузоперевозки и экспедирование (междун. + межгород)")

    # ПВЗ — группировка по бренду (варианты написания склеены)
    pvz = cats["pvz"]
    byb = collections.defaultdict(list)
    disp = {}
    for r in pvz:
        k = bkey(r["name"])
        byb[k].append(r)
        disp.setdefault(k, brand(r["name"]))
    w(u"**Пункты выдачи заказов (`Нуқтаҳои додани фармоишҳои интернетӣ`) — %d**"
      % len(pvz))
    w(u"")
    for k in sorted(byb, key=lambda x: (-len(byb[x]), disp[x].lower())):
        items = sorted(byb[k], key=lambda r: place(r))
        w(u"- **%s** (%d): %s" % (disp[k], len(items),
                                  u" · ".join(
                                      u"[%s](%s)" % (place(r), r["url"])
                                      for r in items)))
    w(u"")

    # Постаматы — по оператору
    pm = cats["postamat"]
    byo = collections.defaultdict(list)
    odisp = {}
    for r in pm:
        k = bkey(r["name"])
        byo[k].append(r)
        odisp.setdefault(k, brand(r["name"]))
    w(u"**Постаматы (`Терминалҳои амонатӣ`) — %d**" % len(pm))
    w(u"")
    for k in sorted(byo, key=lambda x: (-len(byo[x]), odisp[x].lower())):
        items = sorted(byo[k], key=lambda r: place(r))
        w(u"- **%s** (%d): %s" % (odisp[k], len(items),
                                  u" · ".join(
                                      u"[%s](%s)" % (place(r), r["url"])
                                      for r in items)))
    w(u"")

    io.open(OUT, "w", encoding="utf-8", newline="\n").write(u"\n".join(o))
    print("block written: %d lines; pochta=%d exp=%d cargo=%d pvz=%d postamat=%d"
          % (len(o), len(cats["pochta"]), len(cats["exp"]), len(cats["cargo"]),
             len(cats["pvz"]), len(cats["postamat"])))


if __name__ == "__main__":
    main()
