# -*- coding: utf-8 -*-
"""Подбор конкретных цитат под каждый кандидат в новые разделы.

Корни тем дают measure()/draft, но их примеры собраны по частоте совпадений и
попадают на длинные рассылки- FAQ 2022 года. Здесь — детерминированный отбор:
редкие корни весят больше, вопросы из пула лучше, чем ответы, свежие годы лучше,
длинные рассылки штрафуются. Выход — _cand_quotes.txt с готовыми «цитатами»
(#id, дата) для проверки _verify_8a.py.
"""
import io
import json
import math
import os
import re
from collections import Counter

import _cluster_llm as C

OUT = os.path.join(C.HERE, "_cand_quotes.txt")
PER = 8
LONG = re.compile(u"(?i)(закон республи|постановление|http|@|\\\\n)")


def main():
    cands = json.load(io.open(C.CANDSIZES, encoding="utf-8"))
    union = []
    for c in cands:
        for s in c["stems"]:
            if s not in union:
                union.append(s)
    corpus = C.load_corpus()[0]
    dates = {}
    raws = {}
    for r in C.load_jsonl(C.MSGS):
        dates[r["id"]] = (r.get("date") or u"")[:10]
        raws[r["id"]] = r.get("text") or u""
    n = len(corpus)
    df = Counter()
    matched_all = {}
    for mid, year, txt, isq, author in corpus:
        if not txt:
            matched_all[mid] = ()
            continue
        hits = tuple(s for s in union if s in txt)
        matched_all[mid] = hits
        for s in hits:
            df[s] += 1
    idf = dict((s, math.log(float(n) / max(1, df[s]))) for s in union)
    rare = set(s for s in union if df[s] <= 1500)

    lines = []
    for c in cands:
        stems = [s for s in c["stems"]]
        scored = []
        for mid, year, txt, isq, author in corpus:
            hits = matched_all.get(mid) or ()
            m = [s for s in hits if s in stems]
            if len(m) < 2 or not (set(m) & rare):
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
        chosen = []
        seen_auth = set()
        seen_pre = set()
        for sc, mid, author, nm in scored:
            sn = C.snippet(raws.get(mid) or u"")
            if len(sn) < 45 or u"http" in sn.lower():
                continue
            pre = sn[:35].lower()
            if author in seen_auth or pre in seen_pre:
                continue
            seen_auth.add(author)
            seen_pre.add(pre)
            chosen.append((sc, mid, sn, nm))
            if len(chosen) >= PER:
                break
        lines.append(u"## %s" % c["name"])
        lines.append(u"объём: strong=%d hits=%d qhits=%d авторов=%d" % (
            c["strong"], c["hits"], c["qhits"], c["authors"]))
        lines.append(u"кластеры: %s" % u", ".join(c["clusters"][:8]))
        lines.append(u"корни: %s" % u", ".join(stems[:14]))
        lines.append(u"df корней: %s" % u", ".join(
            u"%s:%d" % (s, df[s]) for s in stems[:14]))
        for sc, mid, sn, nm in chosen:
            lines.append(u"  [%.1f/%d] \u00ab%s\u00bb (#%s, %s)" % (
                sc, nm, sn, mid, dates.get(mid)))
        lines.append(u"")
    io.open(OUT, "w", encoding="utf-8", newline=u"\n").write(
        u"\n".join(lines) + u"\n")
    print("quotes for %d candidates -> %s" % (len(cands), os.path.basename(OUT)))
    print("union stems: %d, df rare(<=1500): %d" % (len(union), len(rare)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
