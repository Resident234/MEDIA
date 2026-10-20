# -*- coding: utf-8 -*-
"""Сверить числа прозы раздела «Сверка двух справочников» с массивами.

usage: python prose_numbers.py [--json]

Проза в `_work/build/70_pokupki.md` пишется руками, а карточки между
маркерами перегенерирует `make_md.py`. После ночного прогона (finish_run.py)
массивы Яндекса меняются, и числа, внесённые в прозу словами, устаревают —
этот скрипт по regex вытаскивает их из текста и ставит рядом те же числа,
пересчитанные по `crossmatch_stats.json`, `parse_stats.json` и `cards/`.

Вывод — по строке на проверку: OK / STALE (было → стало) / MISSING (шаблон не
нашёл строку в тексте — значит, формулировку правили и надо добавить шаблон).
Печатается ASCII-escaped, потому что консоль Windows в cp866 падает на кириллице.
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MD = os.path.join(HERE, "..", "build", "70_pokupki.md")


def load(name):
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        return {}
    return json.load(io.open(path, encoding="utf-8"))


def ru_int(n):
    return str(n)


# В прозе числа иногда написаны словами («в трёх разница больше звезды»);
# сравнение нормализует их к цифре, иначе проверка срабатывает ложно.
RUNUM = {"одна": 1, "одной": 1, "две": 2, "двух": 2, "три": 3, "трёх": 3,
         "четыре": 4, "четырех": 4, "пять": 5, "пяти": 5, "шесть": 6,
         "шести": 6, "семь": 7, "семи": 7, "восемь": 8, "восьми": 8,
         "девять": 9, "девяти": 9, "десять": 10, "десяти": 10}


def norm_group(g):
    if g.isdigit():
        return g
    return str(RUNUM.get(g.lower(), g))


def main():
    st = load("crossmatch_stats.json")
    ps = load("parse_stats.json")
    cards = 0
    cdir = os.path.join(HERE, "cards")
    if os.path.isdir(cdir):
        cards = sum(1 for f in os.listdir(cdir)
                    if f.endswith(".json") and os.path.getsize(os.path.join(cdir, f)) > 100)
    text = io.open(MD, encoding="utf-8").read()
    rev = st.get("reverse", {})
    cities = st.get("other_by_city", {})
    pct = st.get("percentiles", {})

    checks = [
        # (описание, шаблон в прозе, ожидаемые значения)
        ("двойники по Душанбе",
         r"по Душанбе, (\d+) из (\d+) стоят в \d+ м и ближе",
         [st.get("dush_twins"), st.get("yx_dushanbe")]),
        ("совпадение имён в парах",
         r"имена при этом совпадают лишь у (\d+)",
         [st.get("dush_twin_names")]),
        ("процентили расстояний",
         r"у 10 % карточек — (\d+) м и меньше, медиана (\d+) м, 90-й процентиль (\d+) м, максимум (\d+) м",
         [pct.get("p10"), pct.get("p50"), pct.get("p90"), pct.get("max")]),
        ("обратное сведение, всего",
         r"из (\d+) карточек 2ГИС, попавших в запрошенные категории, двойника в Яндексе имеют (\d+)",
         [st.get("reverse_total", [None, None])[0], st.get("reverse_total", [None, None])[1]]),
        ("обратно: базары и рынки",
         r"базары и рынки (\d+) из (\d+)",
         [rev.get("базары и рынки", [None, None])[1], rev.get("базары и рынки", [None, None])[0]]),
        ("обратно: торговые центры",
         r"торговые центры (\d+) из (\d+)",
         [rev.get("торговые центры", [None, None])[1], rev.get("торговые центры", [None, None])[0]]),
        ("обратно: гипермаркеты",
         r"гипермаркеты (\d+) из (\d+)",
         [rev.get("гипермаркеты", [None, None])[1], rev.get("гипермаркеты", [None, None])[0]]),
        ("обратно: супермаркеты",
         r"супермаркеты (\d+) из (\d+)",
         [rev.get("супермаркеты", [None, None])[1], rev.get("супермаркеты", [None, None])[0]]),
        ("обратно: пункты выдачи",
         r"пункты выдачи (\d+) из (\d+)",
         [rev.get("пункты выдачи (ПВЗ)", [None, None])[1], rev.get("пункты выдачи (ПВЗ)", [None, None])[0]]),
        ("обратно: ремёсла и сувениры",
         r"ремёсла и сувениры (\d+) из (\d+)",
         [rev.get("ремёсла и сувениры", [None, None])[1], rev.get("ремёсла и сувениры", [None, None])[0]]),
        ("обратно: интернет-магазины",
         r"интернет-магазины и маркетплейсы (\d+) из (\d+)",
         [rev.get("интернет-магазины и маркетплейсы", [None, None])[1],
          rev.get("интернет-магазины и маркетплейсы", [None, None])[0]]),
        ("пары с двумя оценками",
         r"Пар, где оценку имеют оба справочника, всего (\d+)",
         [st.get("both_rated")]),
        ("расхождения больше звезды",
         r"Из \d+ в (\S+) разница больше звезды",
         [len(st.get("disagree", []))]),
        ("строки за пределами Душанбе",
         r"Бохтар (\d+) и ГБАО (\d+)",
         [cities.get("bohtar"),
          sum(v for k, v in cities.items() if "badakhshan" in k or k == "horog")]),
    ]

    out, stale = [], 0
    for name, pat, exp in checks:
        if exp is None:
            continue
        m = re.search(pat, text)
        if not m:
            out.append({"what": name, "status": "MISSING"})
            continue
        got = [norm_group(x) for x in m.groups()]
        want = [ru_int(x) if x is not None else "?" for x in exp]
        status = "OK" if got == want else "STALE"
        if status == "STALE":
            stale += 1
        out.append({"what": name, "status": status, "text": got, "now": want})

    extra = {
        "yx_cards_total": ps.get("cards_total"),
        "yx_cards_priority": ps.get("priority"),
        "yx_named": ps.get("named"),
        "yx_rated": ps.get("rated"),
        "yx_dropped": ps.get("dropped"),
        "yx_cards_opened": cards,
        "yx_rows": st.get("yx_with_coords"),
        "prio_twins": st.get("prio_twins"),
        "named_twins": st.get("named_twins"),
        "named_twin_names": st.get("named_twin_names"),
    }
    if "--json" in sys.argv:
        print(json.dumps({"checks": out, "extra": extra}, ensure_ascii=True, indent=1))
    else:
        for c in out:
            print("%-7s %-34s %s" % (c["status"],
                                     json.dumps(c["what"], ensure_ascii=True)[:34],
                                     json.dumps([c.get("text"), c.get("now")], ensure_ascii=True)))
        print("extra %s" % json.dumps(extra, ensure_ascii=True))
        print("stale: %d" % stale)
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
