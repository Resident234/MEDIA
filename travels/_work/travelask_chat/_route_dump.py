# -*- coding: utf-8 -*-
"""_route_dump.py — recalled-дайджесты для кластеров, которые НЕ стали новыми
разделами, а распределяются по существующим частям путеводителя.

По каждому кластеру (набор topic'ов из _topics_stems.json) собираемunion корней,
меряем документную частоту по корпусу, отбрасываем «мусорные» корни (df>DF_MAX),
скорим сообщения как в _cand_refine (idf-сумма + свежесть + вопрос + длина), и
вываливаем топ сообщений ПОЛНЫМ текстом в _route/<slug>.txt в формате
  id | DD.MM.YYYY | полный текст
Это источник для цитирования: цитируем дословно подряд идущий фрагмент текста,
поэтому гейт _verify_8a.py даёт 1.0.

Console — ASCII. Кириллица только в файлы UTF-8.
"""
import io
import json
import math
import os
import re
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
MSGS = os.path.join(HERE, "messages.jsonl")
STEMS = os.path.join(HERE, "_topics_stems.json")
OUTDIR = os.path.join(HERE, "_route")

DF_MAX = 1500      # корень чаще — общий, не используем для замера
DF_ANCHOR = 700    # хотя бы один корень должен быть реже этого
LONG = re.compile(u"(?i)(http|@|t.me/)")
GENERIC = set([u"таджик", u"душанб", u"худжанд", u"подскаж", u"посовет",
               u"знает", u"ребят", u"здравств", u"пожалу", u"спасиб",
               u"вопрос", u"сообщ", u"интерес", u"очень", u"хочет", u"хочу",
               u"можно", u"нужно", u"какие", u"какой", u"где", u"когда",
               u"как", u"что", u"есть", u"был"])

# кластер -> (slug, часть-назначение, список topic'ов из _topics_stems.json)
CLUSTERS = [
    ("svyaz", "05", u"связь, интернет и соцсети",
     [u"связь, интернет и соцсети", u"связь и интернет",
      u"картографические и навигационные сервисы"]),
    ("money_fx", "03", u"обмен валют и карт",
     [u"обмен валют и карт", u"банковские карты и кошельки"]),
    ("money_transfer", "03", u"денежные переводы и банкоматы",
     [u"денежные переводы и банкоматы", u"переводы денег и банковские услуги"]),
    ("money_crypto", "03", u"криптовалюта и обмен",
     [u"криптовалюта и обмен"]),
    ("money_pay", "03", u"платёжные системы",
     [u"платёжные системы"]),
    ("dostavka_import", "08d", u"ввоз и растаможка товаров",
     [u"ввоз и растаможка товаров"]),
    ("shop_markets", "08a", u"рынки, магазины и маркетплейсы",
     [u"рынки, магазины и маркетплейсы", u"доставка и маркетплейсы",
      u"онлайн-магазины и торговля"]),
    ("border", "1b", u"пограничные переходы и контроль",
     [u"пограничные переходы и контроль", u"граница и контроль"]),
    ("place_khorog", "06", u"поездка в Хорог и по Памиру",
     [u"поездки в хорог", u"гиды"]),
    ("place_active", "06", u"активный отдых",
     [u"рыбалка и активный отдых", u"бассейны и аквапарки"]),
    ("place_seismic", "06", u"землетрясения, лавины, сели",
     [u"землетрясения"]),
    ("trans_price", "04", u"цены на транспорт и маршруты",
     [u"цены на транспорт и маршруты"]),
    ("trans_avia", "04", u"авиаперелёты и ручная кладь",
     [u"авиаперелеты и транспорт в ручную кладь"]),
    ("trans_intercity", "04", u"междугородний транспорт и маршруты",
     [u"междугородний транспорт и маршруты"]),
    ("med_services", "11", u"медицинские услуги",
     [u"пцр и медицинские услуги", u"пцр тесты и медицинские справки"]),
]

# Тонкие кластеры: у topic'ов слишком генеричные/редкие корни, дополняем доменными
# stem'ами и ослабляем порог до 1 совпадения (но обязательно с якорем).
EXTRA = {
    "money_pay": [u"paypal", u"payeer", u"payoneer", u"юмани", u"qiwi",
                  u"webmon", u"эквайр", u"платформ", u"платежн", u"moneto"],
    "place_seismic": [u"землетр", u"толчок", u"магнитуд", u"сейсмич", u"подземн",
                      u"лавин", u"оползн", u"обвал", u"камнепад", u"селев",
                      u"сход", u"разруш", u"эпицентр", u"бeзоп"],
}
MIN1 = set(EXTRA.keys())


def norm(s):
    s = (s or u"").lower().replace(u"ё", u"е")
    return re.sub(u"[^a-zа-я0-9]+", u" ", s).strip()


def clean_stem(s):
    s = re.sub(u"[^a-zа-я]", u"", norm(s))[:8]
    return s if len(s) >= 5 and s not in GENERIC else None


def fallback_stems(name):
    """если у topic'а нет сохранённых корней — нарезаем из названия."""
    out = []
    for w in norm(name).split():
        st = clean_stem(w)
        if st and st not in out:
            out.append(st)
    return out


def main():
    if not os.path.isdir(OUTDIR):
        os.makedirs(OUTDIR)
    stems_by_topic = json.load(io.open(STEMS, encoding="utf-8"))
    # корпус
    rows = []
    for line in io.open(MSGS, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        m = json.loads(line)
        txt = re.sub(u"\\s+", u" ", m.get("text") or u"")
        ym = re.search(u"(\\d{4})", m.get("date") or u"")
        rows.append((int(m["id"]), (m.get("date") or u"")[:10],
                     ym.group(1) if ym else u"??", txt,
                     (m.get("text") or u"").strip().endswith(u"?")))
    n = len(rows)
    # единый словарь корней по всем кластерам -> df
    union = []
    for _slug, _part, title, topics in CLUSTERS:
        for tp in topics:
            for s in (stems_by_topic.get(tp, {}).get("stems")
                      or fallback_stems(tp)):
                st = clean_stem(s)
                if st and st not in union:
                    union.append(st)
        for s in EXTRA.get(_slug, []):
            st = clean_stem(s)
            if st and st not in union:
                union.append(st)
    df = Counter()
    norm_texts = []
    for rid, date, year, txt, isq in rows:
        nt = norm(txt)
        norm_texts.append(nt)
        for s in union:
            if s in nt:
                df[s] += 1
    idf = dict((s, math.log(float(n) / max(1, df[s]))) for s in union)

    index = {rid: (date, txt) for rid, date, year, txt, isq in rows}
    yearmap = {rid: year for rid, date, year, txt, isq in rows}

    for slug, part, title, topics in CLUSTERS:
        spec_all = []
        for tp in topics:
            for s in (stems_by_topic.get(tp, {}).get("stems")
                      or fallback_stems(tp)):
                st = clean_stem(s)
                if st and st not in spec_all:
                    spec_all.append(st)
        for s in EXTRA.get(slug, []):
            st = clean_stem(s)
            if st and st not in spec_all:
                spec_all.append(st)
        need = 1 if slug in MIN1 else 2
        spec = [s for s in spec_all if df[s] <= DF_MAX]
        anchors = set(s for s in spec if df[s] <= DF_ANCHOR)
        scored = []
        for i, (rid, date, year, txt, isq) in enumerate(rows):
            nt = norm_texts[i]
            m = [s for s in spec if s in nt]
            if len(m) < need:
                continue
            if not (set(m) & anchors):
                continue
            sc = sum(idf[s] for s in m)
            if isq:
                sc += 2.0
            if year in (u"2025", u"2026"):
                sc += 1.5
            elif year == u"2024":
                sc += 0.8
            L = len(txt)
            if 55 <= L <= 300:
                sc += 1.2
            elif L > 460:
                sc -= 2.0
            if LONG.search(txt):
                sc -= 1.5
            scored.append((sc, rid, L))
        scored.sort(key=lambda x: (-x[0], x[1]))
        lines = [u"=== %s -> часть %s | spec=%s | scored=%d" % (
            title, part, u",".join(spec[:14]), len(scored))]
        shown = 0
        for sc, rid, L in scored:
            date, txt = index[rid]
            if L < 28:
                continue
            lines.append(u"%d | %s | %.1f | %s" % (rid, date, sc, txt))
            shown += 1
            if shown >= 70:
                break
        path = os.path.join(OUTDIR, "%s.txt" % slug)
        io.open(path, "w", encoding="utf-8", newline="\n").write(
            u"\n".join(lines) + u"\n")
        print("%-16s part=%s spec=%2d scored=%4d dumped=%d -> _route/%s.txt"
              % (slug, part, len(spec), len(scored), shown, slug))


if __name__ == "__main__":
    main()
