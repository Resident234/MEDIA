# -*- coding: utf-8 -*-
"""Сводные числа по всем шагам кластеризации — для раздела «как считали»."""
import io
import json
import os
import re
from collections import Counter

import _cluster_llm as C

OUT = os.path.join(C.HERE, "_cluster_stats.txt")

RE_YEAR = re.compile(r"(\d{4})")


def main():
    rep = []
    w = rep.append
    rows = C.load_jsonl(C.MSGS)
    years = Counter(RE_YEAR.search(r.get("date") or u"").group(1)
                    for r in rows
                    if r.get("date") and RE_YEAR.search(r.get("date")))
    w(u"corpus messages: %d, years: %s" % (
        len(rows), u", ".join(u"%s:%d" % kv for kv in sorted(years.items()))))
    pool = C.load_jsonl(C.POOL)
    w(u"pool (topic-defining): %d" % len(pool))
    bo = C.load_jsonl(os.path.join(C.HERE, "_boiler_excluded.jsonl"))
    w(u"boiler excluded: %d" % len(bo))
    samp = C.load_jsonl(C.SAMPLE)
    w(u"sample: %d" % len(samp))
    lab = C.load_jsonl(C.LABELS)
    keep = C.kept_ids()
    use = [r for r in lab if r.get("id") in keep and r.get("c") is not None]
    w(u"label rows: %d, usable: %d" % (len(lab), len(use)))
    cc = Counter(r["c"] for r in use)
    zero = cc.get(0, 0)
    w(u"c=0 (не покрыто): %d (%.1f%% из usable)" % (
        zero, 100.0 * zero / max(1, len(use))))
    w(u"распределение c: %s" % u", ".join(
        u"%s:%d" % (k, v) for k, v in sorted(cc.items())))
    free = C.load_jsonl(C.FREE)
    ok_b = set(r["b"] for r in free)
    resid = [r for r in C.load_jsonl(C.RESID) if not C.CHATMETA.search(r["text"])]
    w(u"residual (детерминированный): %d из %d pool (%.1f%%)" % (
        len(resid), len(pool), 100.0 * len(resid) / max(1, len(pool))))
    w(u"free sweep: %d записей, %d/%d пачек по 45 (%d сообщений), %d тем" % (
        len(free), len(ok_b), (len(resid) + 44) // 45, len(ok_b) * 45,
        len(C.vocab_all())))
    merged = json.load(io.open(C.MERGED, encoding="utf-8"))["clusters"]
    w(u"merge: %d кластеров из %d тем головы словаря" % (
        len(merged), sum(len(m.get("members", [])) for m in merged)))
    cl = C.clusters_from_labels()
    st = C.load_stems()
    w(u"кластеров всего: %d, с корнями: %d, вес>=3: %d" % (
        len(cl), len(st), sum(1 for c in cl if c["weight"] >= 3)))
    if os.path.exists(C.SIZES):
        sized = json.load(io.open(C.SIZES, encoding="utf-8"))
        w(u"sized: %d, strong>=30: %d, strong>=100: %d" % (
            len(sized), sum(1 for s in sized if s["strong"] >= 30),
            sum(1 for s in sized if s["strong"] >= 100)))
    if os.path.exists(C.RANKS):
        rk = C.load_jsonl(C.RANKS)
        w(u"rank: %d предложений от %d моделей" % (
            len(rk), len(set(r.get("model") for r in rk))))
    if os.path.exists(C.CANDSIZES):
        cs = json.load(io.open(C.CANDSIZES, encoding="utf-8"))
        w(u"measured candidates: %d" % len(cs))
    io.open(OUT, "w", encoding="utf-8", newline=u"\n").write(
        u"\n".join(rep) + u"\n")
    print("stats written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
