# -*- coding: utf-8 -*-
"""One-line-per-gym ASCII dump for writing the guide subsection.

Merges final.jsonl (list+card extract) with the raw card dumps in cards/,
pulling the "Время работы" line that the card renders as a current-state
phrase ("Открыто до 23:00") or "График работы не указан".
Console output is ASCII-only (cp866-safe); Cyrillic goes to _report.txt.
"""
import glob
import io
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def hours(d):
    for x in d.get("contactBlock") or []:
        if "Время работы" in x:
            s = x.replace("Время работы", "").replace("График", "").strip()
            return s or None
        if x.strip() == "Время работы":
            continue
    for x in d.get("contactBlock") or []:
        if "не указан" in x:
            return "не указан"
    return None


def main():
    cards = {}
    for p in glob.glob(os.path.join(HERE, "cards", "*.json")):
        d = json.load(io.open(p, encoding="utf-8-sig"))
        cards[os.path.basename(p)[:-5]] = d
    rows = [json.loads(l) for l in io.open(os.path.join(HERE, "final.jsonl"),
                                           encoding="utf-8") if l.strip()]
    out = []
    for r in rows:
        d = cards.get(r["id"], {})
        r["hours_now"] = hours(d)
        r["btns"] = d.get("btns")
        out.append(r)
    txt = "\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n"
    io.open(os.path.join(HERE, "_report.txt"), "w", encoding="utf-8").write(txt)
    for r in out:
        line = "%-26s %s rev=%-3s wa=%s tg=%s wsite=%s tsite=%s phones=%s hours=%s social=%d notes=%d" % (
            r["name"][:26], r["rating"], r["reviews"],
            "Y" if r["whatsapp"] else "-", "Y" if r["telegram"] else "-",
            "Y" if r["whatsapp_site"] else "-", "Y" if r["telegram_site"] else "-",
            len(r["phones"]), json.dumps(r["hours_now"])[:22], len(r["social_other"]),
            len(r["site_msg_notes"]))
        print(line.encode("ascii", "backslashreplace").decode())
    print("rows=%d -> _report.txt" % len(out))
    print("hours seen:", json.dumps([re.sub(r"\D", "", h["hours_now"] or "")[:4]
                                     for h in out]).encode("ascii", "backslashreplace").decode())


if __name__ == "__main__":
    main()
