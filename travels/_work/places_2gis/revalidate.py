# -*- coding: utf-8 -*-
"""Перепроверить `kind: hit` в places_2gis/rows.jsonl более строгим
сопоставлением имён. Сносит в `nomatch` ложные попадания вроде
«Стиль» → «Стиль Групп мебель».

usage: python revalidate.py
"""
import io
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = os.path.join(HERE, "..", "places_2gis", "rows.jsonl")
BAK = ROWS + ".bak"


def norm(txt):
    if not txt:
        return ""
    txt = txt.lower()
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r"ё", "е", txt)
    txt = re.sub(r"[^a-z0-9\u0430-\u044f\s]", " ", txt)
    return " ".join(txt.split())


def tokens(txt):
    return set(t for t in norm(txt).split() if len(t) >= 3)


def plausible(want, got):
    wt, gt = tokens(want), tokens(got)
    if not wt or not gt:
        return False
    if len(wt) == 1:
        return norm(want) == norm(got)
    if wt <= gt or gt <= wt:
        return True
    inter = len(wt & gt)
    union = len(wt | gt)
    return bool(union and inter * 2 >= union)


def main():
    os.rename(ROWS, BAK)
    fh = io.open(ROWS, "w", encoding="utf-8", newline="\n")
    kept = demoted = 0
    for line in io.open(BAK, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            fh.write(line)
            continue
        if r.get("kind") == "hit":
            if not plausible(r.get("name"), r.get("card_name")):
                r["kind"] = "nomatch"
                r["demoted_by"] = "revalidate"
                demoted += 1
            else:
                kept += 1
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    fh.close()
    print("hits kept=%d demoted=%d" % (kept, demoted))


if __name__ == "__main__":
    main()
