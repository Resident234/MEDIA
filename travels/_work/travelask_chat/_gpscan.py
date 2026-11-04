# -*- coding: utf-8 -*-
"""_gpscan.py — точечный поиск по messages.jsonl для раздела 1b «Граница и КПП».

Выборка строится по явным маркерам темы (названия КПП, слова «погран*/границ*/
пропуск/очередь/штамп/закрытие»), поэтому в отличие от IDF-дайджеста
_route/border.txt даёт именно фактуру о переходах, а не общие вопросы.
Формат вывода:  id | DD.MM.YYYY | len | полный текст
Console ASCII, кириллица только в UTF-8 файлы.
"""
import io
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
MSGS = os.path.join(HERE, "messages.jsonl")
OUT = os.path.join(HERE, "_route", "border_gpscan.txt")

# названия переходов и устойчивые выражения
NAMES = [
    u"кзыл-арт", u"кызыл-арт", u"кзыл-бель", u"кызыл-бель", u"мургаб", u"мургаб",
    u"айбек", u"ойбек", u"патар", u"джартепа", u"жартепа", u"саразм", u"сарб",
    u"тосакаде", u"tosha", u"конистадон", u"джавала", u"рауат", u"обшорон",
    u"культепе", u"камыс", u"карамык", u"сарыасия", u"сары-асия", u"братство",
    u"нижний-панж", u"панж", u"хавастабад", u"зафарабад", u"серох", u"тулчгар",
    u"гунт", u"шуроб", u"куляб-айбек",
]
TERMS = [
    u"погранпереход", u"погранперех", u"погранпост", u"погран контрол",
    u"пограничный переход", u"погран переход", u"погран пост", u"кпп ", u"кпп,",
    u"кпп-", u"пропускной пункт", u"погранслужб", u"пограничник",
    u"пограничный контроль", u"пограничный пост", u"пограничны",
    u"пересечени", u"пересечь", u"переход границ", u"погран границ",
    u"график работы", u"часы работы", u"закрыт", u"открыт", u"не работает",
    u"ограничен", u"приостанов", u"режим работы", u"светлое время",
    u"очеред", u"часа ожидан", u"пешком через", u"штамп", u"миграционную карт",
    u"миграционная карт", u"погранслужб", u"пропуск в гбао", u"спецразрешен",
    u"разрешени", u"досмотр", u"таможенн", u"красный коридор", u"зеленый коридор",
]
CITE = re.compile(r"#(\d+)")


def main():
    cited = set()
    for fn in ("10_viza.md", "15_tamozhnya.md", "20_zhile.md", "40_transport.md",
               "91_med_chat.md", "50_places_intro.md", "73_dostavka.md",
               "71_pokupki_chat.md"):
        p = os.path.join(HERE, "..", "build", fn)
        if os.path.exists(p):
            cited |= set(CITE.findall(io.open(p, encoding="utf-8").read()))
    rows = []
    for line in io.open(MSGS, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        m = json.loads(line)
        raw = m.get("text") or u""
        txt = re.sub(u"\\s+", u" ", raw)
        low = txt.lower().replace(u"ё", u"е")
        hits = [k for k in NAMES if k in low]
        terms = [k for k in TERMS if k in low]
        if not hits:
            continue
        if len(terms) < 1:
            continue
        if str(m["id"]) in cited:
            continue
        rows.append((len(hits) * 3 + len(terms), int(m["id"]),
                     (m.get("date") or u"")[:10], len(txt), txt))
    rows.sort(key=lambda x: (-x[0], x[2]))
    lines = []
    for sc, rid, date, L, txt in rows:
        if L < 40:
            continue
        lines.append(u"%d | %s | %d | %s" % (rid, date, sc, txt))
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(
        u"\n".join(lines) + u"\n")
    print("gpscan rows=%d -> _route/border_gpscan.txt" % len(lines))


if __name__ == "__main__":
    main()
