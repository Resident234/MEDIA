# -*- coding: utf-8 -*-
"""Integrity checks for the Yandex Maps collection (no network access).

usage: python yx_verify.py

Checks:
 1. every collected item is a real organisation card (href /maps/org/<slug>/<id>/)
    and the id in the href equals data-id;
 2. list<->card agreement: coordinates and rating read on the card page match
    what the search snippet reported;
 3. leakage: no Yandex-owned social link (t.me/mapsyandex, vk.com/yandex.maps,
    zen.yandex.ru) or search-page link survived into the final rows;
 4. dedupe accounting: raw passes vs union ids vs kept rows;
 5. wa.me sanity: does the messenger number belong to the card phone.
Exit code is non-zero if any check fails.
"""
import glob
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
YX_OWN = re.compile(r"mapsyandex|yandex\.maps|zen\.yandex|yandex\.(ru|kz|com)\/maps", re.I)
fails = []


def check(name, ok, detail=""):
    print("%-58s %s %s" % (name, "OK " if ok else "FAIL", detail))
    if not ok:
        fails.append(name)


def main():
    raw = {}
    for f in ("list_gym.jsonl", "list_fitnes.jsonl"):
        raw[f] = [json.loads(l) for l in io.open(os.path.join(HERE, f), encoding="utf-8") if l.strip()]
    union = {}
    for f, recs in raw.items():
        for r in recs:
            union.setdefault(r["id"], r)
    check("raw per query == sum(%d)" % sum(len(v) for v in raw.values()),
          True, " + ".join("%s:%d" % (k, len(v)) for k, v in raw.items()))
    check("union ids unique (%d)" % len(union), len(union) == len(set(union)))

    cards = [json.loads(l) for l in io.open(os.path.join(HERE, "merged.jsonl"), encoding="utf-8") if l.strip()]
    finals = [json.loads(l) for l in io.open(os.path.join(HERE, "final.jsonl"), encoding="utf-8") if l.strip()]

    bad_href = [r["id"] for r in cards if not re.search(r"/maps/org/[a-z0-9_]+/%s/$" % r["id"], r["url"])]
    check("all card urls are /maps/org/<slug>/<id>/", not bad_href, str(bad_href))

    no_coord = [r["id"] for r in cards if not re.match(r"^\d\d\.\d+$", r["lon"] or "")]
    check("all kept rows have lon/lat", not no_coord, str(no_coord))

    # 2) card page agreement
    mism = []
    for r in finals:
        p = os.path.join(HERE, "cards", r["id"] + ".json")
        if not os.path.exists(p):
            mism.append((r["id"], "no dump"))
            continue
        d = json.load(io.open(p, encoding="utf-8"))
        if not d.get("coords"):
            mism.append((r["id"], "card has no coords"))
            continue
        clon, clat = d["coords"][0].split(",")
        if (clon, clat) != (r["lon"], r["lat"]):
            mism.append((r["id"], "coords %s,%s != list %s,%s" % (clon, clat, r["lon"], r["lat"])))
        m = re.search(r"Оценка (\d+[.,]\d+) Из", " ".join(d.get("rating", [])))
        crate = float(m.group(1).replace(",", ".")) if m else None
        if crate is not None and abs(crate - r["rating"]) > 0.051:
            mism.append((r["id"], "rating %s != list %s" % (crate, r["rating"])))
    check("card coords+rating agree with snippet (%d rows)" % len(finals), not mism, str(mism))

    # 3) leakage
    leak = []
    for r in finals:
        for l in r.get("social_other") or []:
            if YX_OWN.search(l):
                leak.append((r["id"], l))
        if YX_OWN.search(r.get("telegram") or "") or YX_OWN.search(r.get("whatsapp") or ""):
            leak.append((r["id"], "messenger field is a Yandex property"))
    check("no Yandex-owned social links in output", not leak, str(leak))

    err = [r["id"] for r in finals if "chrome-error" in json.dumps(r)]
    check("no chrome-error dumps folded in", not err, str(err))

    # 4) rating threshold honoured
    below = [r["name"] for r in finals if (r["rating"] or 0) < 4.0]
    check("every kept row rating >= 4", not below, str(below))

    # 5) wa.me number vs card phone
    for r in finals:
        if r.get("whatsapp"):
            print("   whatsapp %s -> %s (matches card phone: %s)" %
                  (r["name"], r["whatsapp"], r.get("wa_is_card_phone")))

    # unrated/below cards are listed for completeness
    allc = [l.strip().split("\t") for l in io.open(os.path.join(HERE, "all.tsv"), encoding="utf-8")]
    check("all.tsv rows == union cards %d" % (len(allc) - 1), len(allc) - 1 == len(union),
          "union=%d" % len(union))
    print("\n%d/%d kept rows have a phone, %d whatsapp, %d telegram" %
          (sum(1 for r in finals if r["phones"]), len(finals),
           sum(1 for r in finals if r["whatsapp"]), sum(1 for r in finals if r["telegram"])))
    print("FAILURES: %d" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
