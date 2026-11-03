# -*- coding: utf-8 -*-
"""Уточнённый замер кандидатов: без размывания общими словами.

В _cand_sizes.json среди корней кандидатов есть высокочастотные слова
(регистри-, телефон, получ-, приложе-), из-за чего strong завышен в разы. Здесь для каждого
корня считается документная частота по всему корпусу, «мусорные» корни (df >
DF_MAX) отбрасываются, объём перемеряется только по оставшимся, и заново
подбираются цитаты — уже по редким корням.

Выход: _cand_refine.txt (для чтения) и _cand_refined.json (для сборки md).
"""
import io
import json
import math
import os
import re
from collections import Counter

import _cluster_llm as C

OUT_TXT = os.path.join(C.HERE, "_cand_refine.txt")
OUT_JSON = os.path.join(C.HERE, "_cand_refined.json")
DF_MAX = 1200          # корень чаще считают общим и не используют для замера
DF_ANCHOR = 600        # хотя бы один корень должен быть реже этого
PER = 6
LONG = re.compile(u"(?i)(закон республи|постановление|http|@)")


def main():
    cands = json.load(io.open(C.CANDSIZES, encoding="utf-8"))
    union = []
    for c in cands:
        for s in C.clean_stems(c["stems"]):
            if s not in union:
                union.append(s)
    corpus, _ = C.load_corpus()
    dates = {}
    raws = {}
    for r in C.load_jsonl(C.MSGS):
        dates[r["id"]] = (r.get("date") or u"")[:10]
        raws[r["id"]] = r.get("text") or u""
    n = len(corpus)
    df = Counter()
    matched = {}
    for mid, year, txt, isq, author in corpus:
        hits = tuple(s for s in union if s in txt) if txt else ()
        matched[mid] = hits
        for s in hits:
            df[s] += 1
    idf = dict((s, math.log(float(n) / max(1, df[s]))) for s in union)

    out = []
    lines = []
    for c in cands:
        allst = C.clean_stems(c["stems"])
        spec = [s for s in allst if df[s] <= DF_MAX]
        dropped = [s for s in allst if df[s] > DF_MAX]
        anchors = set(s for s in spec if df[s] <= DF_ANCHOR)
        hits = strong = qhits = 0
        authors = set()
        years = Counter()
        scored = []
        for mid, year, txt, isq, author in corpus:
            h = matched.get(mid) or ()
            if not spec or not (set(h) & set(spec)):
                continue
            hits += 1
            m = [s for s in h if s in spec]
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
        chosen = []
        seen_auth = set()
        seen_pre = set()
        for sc, mid, author, nm in scored:
            sn = C.snippet(raws.get(mid) or u"")
            if len(sn) < 50 or u"http" in sn.lower():
                continue
            pre = sn[:35].lower()
            if author in seen_auth or pre in seen_pre:
                continue
            seen_auth.add(author)
            seen_pre.add(pre)
            chosen.append({"score": round(sc, 1), "id": mid,
                           "date": dates.get(mid), "sn": sn, "n": nm})
            if len(chosen) >= PER:
                break
        rec = {"name": c["name"], "priority": c.get("priority"),
               "closer": c.get("closer"), "model": c.get("model"),
               "scope": c.get("scope"), "why": c.get("why"),
               "risk": c.get("risk"), "clusters": c["clusters"],
               "stems_spec": spec, "stems_dropped": dropped,
               "df": dict((s, df[s]) for s in allst),
               "hits": hits, "strong": strong, "qhits": qhits,
               "authors": len(authors), "years": dict(years),
               "strong_old": c["strong"], "quotes": chosen}
        out.append(rec)

    out.sort(key=lambda x: -x["strong"])
    for r in out:
        lines.append(u"## %s" % r["name"])
        lines.append(u"priority=%s closer=%s model=%s" %
                     (r["priority"], r["closer"], r["model"]))
        lines.append(u"объём: strong=%d (было %d) hits=%d qhits=%d авторов=%d" %
                     (r["strong"], r["strong_old"], r["hits"], r["qhits"],
                      r["authors"]))
        lines.append(u"годы: %s" % u", ".join(
            u"%s:%d" % kv for kv in sorted(r["years"].items())))
        lines.append(u"редкие корни: %s" % u", ".join(
            u"%s:%d" % (s, r["df"][s]) for s in r["stems_spec"][:12]))
        lines.append(u"отброшено (df>%d): %s" % (DF_MAX, u", ".join(
            u"%s:%d" % (s, r["df"][s]) for s in r["stems_dropped"][:12])))
        lines.append(u"кластеры: %s" % u", ".join(r["clusters"][:8]))
        lines.append(u"scope: %s" % (r["scope"] or u""))
        lines.append(u"why: %s" % (r["why"] or u""))
        lines.append(u"risk: %s" % (r["risk"] or u""))
        lines.append(u"цитаты:")
        for q in r["quotes"]:
            lines.append(u"  [%.1f/%d] \u00ab%s\u00bb (#%s, %s)" %
                         (q["score"], q["n"], q["sn"], q["id"], q["date"]))
        lines.append(u"")
    io.open(OUT_TXT, "w", encoding="utf-8", newline=u"\n").write(
        u"\n".join(lines) + u"\n")
    json.dump(out, io.open(OUT_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("refined %d candidates -> %s" % (len(out), os.path.basename(OUT_TXT)))
    print("union stems %d, spec (df<=%d) %d" %
          (len(union), DF_MAX, sum(1 for s in union if df[s] <= DF_MAX)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
