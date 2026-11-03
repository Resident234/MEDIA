# -*- coding: utf-8 -*-
"""Склейка кандидатов и честный замер склеенных групп.

22 предложения от двух моделей — это 12 уникальных тем (каждая продублирована
вторая моделью с другим названием). Здесь группы склеиваются по списку parts,
объём считается по объединению редких корней (без двойного счёта одних и тех же
сообщений) и подбираются цитаты под каждую группу.

Выход: _cand_groups.txt (для чтения) и _cand_groups.json (для сборки md).
"""
import io
import json
import math
import os
import re
from collections import Counter

import _cluster_llm as C

OUT_TXT = os.path.join(C.HERE, "_cand_groups.txt")
OUT_JSON = os.path.join(C.HERE, "_cand_groups.json")
DF_MAX = 1200
DF_ANCHOR = 600
PER = 7
LONG = re.compile(u"(?i)(закон республи|постановление|http|@)")

# группа -> (имена кандидатов из _cand_refined.json, кластеры-дополнения,
#            override-корни). Если override задан, корни берются только из него.
GROUPS = [
    (u"Гражданство, ВНЖ, депортация и миграционные запреты",
     [u"миграция и гражданство", u"гражданство и миграция"],
     [u"прописка и регистрация граждан"], None),
    (u"Автомобиль: правила, документы, руль и тонировка",
     [u"авто: правила и документы", u"автомобильные вопросы"],
     [u"право руля и тонировка авто", u"автомобильное обслуживание и запчасть"],
     None),
    (u"Консульство, нотариат, апостиль и легализация",
     [u"консульство и юридические услуги", u"визовые и консульские услуги",
      u"нотариальные и доверительные услуги"],
     [u"консульские и посольские услуги", u"замена и получение документов",
      u"доверенности", u"нотариальные услуги"], None),
    (u"Онлайн-заказы, доставка и пересылка посылок",
     [u"онлайн\u2011шоппинг и доставка", u"доставка и логистика посылок"],
     [u"доставка и маркетплейсы"], None),
    (u"Таможня: ввоз товаров, техники и наличных",
     [u"таможенное оформление и ввоз", u"таможня и ввоз товаров"],
     [u"растаможка и таможенные процедуры", u"ввоз и растаможка товаров",
      u"провоз наличных через границу", u"таможенное оформление техники"], None),
    (u"Карты, кошельки, переводы и крипта",
     [u"банковские карты и электронные кошельки"],
     [u"криптовалюта и обмен"], None),
    (u"Офлайн-карты и навигация в дороге", [], [],
     [u"яндекс", u"гугл", u"офлайн", u"навигац", u"картогр", u"адресна",
      u"2гис", u"маршрут", u"координат", u"адрес"]),
    (u"Доступ к заблокированным сервисам: VPN, роуминг, мессенджеры", [], [],
     [u"vpn", u"впн", u"прокси", u"блокир", u"зеркал", u"роумин",
      u"телеграм", u"мессендж", u"вац", u"инстагр", u"ютуб"]),
    (u"Попутчики и совместные поездки",
     [u"попутки и совместные поездки", u"попутчики и совместные поездки"],
     [u"попутка и совместные поездки"], None),
    (u"Работа, ИНН и открытие бизнеса",
     [u"поиск работы и открытие бизнеса"],
     [u"поиск работы и специалистов", u"поиск работы и трудоустройство",
      u"открытие бизнеса и инн"], None),
    (u"Гиды, трансфер и организованные поездки", [],
     [u"гиды"],
     [u"гид", u"экскурсовод", u"турагент", u"туропер", u"экскурс",
      u"путевка", u"сопровож", u"трансфер", u"поход", u"рюкзак",
      u"треккинг", u"портер"]),
    (u"Домашние животные: перевозка и содержание", [],
     [u"перевозка животных"],
     [u"животн", u"собак", u"кошк", u"ветеринар", u"привив", u"карантин",
      u"клетк", u"переноск", u"чип"]),
    (u"Досуг вне маршрута: бассейны, аквапарки, пляжи, кинотеатры", [],
     [u"бассейны и аквапарки", u"развлечения и досуг"],
     [u"бассейн", u"аквапарк", u"купаться", u"пляж", u"караоке",
      u"кинотеатр", u"баня", u"рыбалк", u"абонемен", u"шезлонг",
      u"раздевал", u"водохран"]),
    (u"Медицинские справки, тесты и форматы документов",
     [u"медицинские справки и пцр", u"медицинские тесты и справки"],
     [u"пцр и медицинские услуги"], None),
    (u"Школы, курсы и образование",
     [u"школы и образование", u"образование и школы"],
     [u"образование и обучение"], None),
    (u"Табак, сигареты и аксессуары", [u"табак и аксессуары"],
     [u"товары для курения"], None),
]


def raw_stems(items):
    """override-корни: без фильтра по длине (vpn, впн, гид, 2гис)"""
    out = []
    for s in items:
        s = re.sub(u"[^a-zа-яё0-9]", u"", C.norm_text(s))
        if s and s not in out:
            out.append(s)
    return out


def df_of(union, corpus):
    df = Counter()
    matched = {}
    for mid, year, txt, isq, author in corpus:
        hits = tuple(s for s in union if s in txt) if txt else ()
        matched[mid] = hits
        for s in hits:
            df[s] += 1
    return df, matched


def main():
    refined = json.load(io.open(os.path.join(C.HERE, "_cand_refined.json"),
                                encoding="utf-8"))
    by_name = dict((r["name"], r) for r in refined)
    sized = dict((s["name"], s) for s in json.load(io.open(C.SIZES,
                                                           encoding="utf-8")))
    corpus, _ = C.load_corpus()
    dates = {}
    raws = {}
    for r in C.load_jsonl(C.MSGS):
        dates[r["id"]] = (r.get("date") or u"")[:10]
        raws[r["id"]] = r.get("text") or u""

    union_all = []
    for grp in GROUPS:
        _, parts, cls, override = grp
        if override:
            for s in raw_stems(override):
                if s not in union_all:
                    union_all.append(s)
            continue
        for p in parts:
            for s in by_name.get(p, {}).get("stems_spec", []):
                if s not in union_all:
                    union_all.append(s)
        for cn in cls:
            for s in C.clean_stems(sized.get(cn, {}).get("stems", [])):
                if s not in union_all:
                    union_all.append(s)
    df, matched = df_of(union_all, corpus)
    idf = dict((s, math.log(float(len(corpus)) / max(1, df[s]))) for s in union_all)

    out = []
    for grp in GROUPS:
        name, parts, cls, override = grp
        stems = []
        if override:
            stems = [s for s in raw_stems(override) if df[s] <= DF_MAX]
        else:
            for p in parts:
                for s in by_name.get(p, {}).get("stems_spec", []):
                    if s not in stems:
                        stems.append(s)
            for cn in cls:
                for s in C.clean_stems(sized.get(cn, {}).get("stems", [])):
                    if df[s] <= DF_MAX and s not in stems:
                        stems.append(s)
            stems = [s for s in stems if df[s] <= DF_MAX]
        anchors = set(s for s in stems if df[s] <= DF_ANCHOR)
        hits = strong = qhits = 0
        authors = set()
        years = Counter()
        scored = []
        for mid, year, txt, isq, author in corpus:
            h = matched.get(mid) or ()
            m = [s for s in h if s in stems]
            if not m:
                continue
            hits += 1
            if len(m) < 2:
                continue
            strong += 1
            authors.add(author)
            years[year] += 1
            if isq:
                qhits += 1
            if not (set(m) & anchors):
                continue
            raw = raws.get(mid) or u""
            L = len(txt)
            sc = sum(idf[s] for s in m)
            if isq:
                sc += 2.0
            if year in (u"2025", u"2026"):
                sc += 1.5
            elif year == u"2024":
                sc += 0.8
            if 55 <= L <= 260:
                sc += 1.2
            elif L > 420:
                sc -= 2.5
            if LONG.search(raw):
                sc -= 1.5
            scored.append((sc, mid, author, len(m)))
        scored.sort(key=lambda x: (-x[0], x[1]))
        quotes = []
        seen_auth = set()
        seen_pre = set()
        for sc, mid, author, nm in scored:
            sn = C.snippet(raws.get(mid) or u"")
            if len(sn) < 55 or u"http" in sn.lower():
                continue
            pre = sn[:35].lower()
            if author in seen_auth or pre in seen_pre:
                continue
            seen_auth.add(author)
            seen_pre.add(pre)
            quotes.append({"score": round(sc, 1), "id": mid,
                           "date": dates.get(mid), "sn": sn, "n": nm})
            if len(quotes) >= PER:
                break
        rec = {"name": name, "parts": parts, "clusters": cls,
               "stems": stems, "df": dict((s, df[s]) for s in stems),
               "hits": hits, "strong": strong, "qhits": qhits,
               "authors": len(authors), "years": dict(years),
               "strong_parts": sum(by_name[p]["strong"] for p in parts
                                   if p in by_name),
               "quotes": quotes}
        out.append(rec)

    out.sort(key=lambda x: -x["strong"])
    lines = []
    for r in out:
        lines.append(u"## %s" % r["name"])
        lines.append(u"объём: strong=%d (сумма по частям %d) hits=%d qhits=%d "
                     u"авторов=%d" % (r["strong"], r["strong_parts"], r["hits"],
                                      r["qhits"], r["authors"]))
        lines.append(u"годы: %s" % u", ".join(
            u"%s:%d" % kv for kv in sorted(r["years"].items())))
        lines.append(u"корни: %s" % u", ".join(
            u"%s:%d" % (s, r["df"][s]) for s in r["stems"][:16]))
        lines.append(u"кластеры: %s" % u", ".join(r["clusters"][:8]))
        lines.append(u"цитаты:")
        for q in r["quotes"]:
            lines.append(u"  [%.1f/%d] \u00ab%s\u00bb (#%s, %s)" %
                         (q["score"], q["n"], q["sn"], q["id"], q["date"]))
        lines.append(u"")
    io.open(OUT_TXT, "w", encoding="utf-8", newline=u"\n").write(
        u"\n".join(lines) + u"\n")
    json.dump(out, io.open(OUT_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("groups: %d -> %s" % (len(out), os.path.basename(OUT_TXT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
