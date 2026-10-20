# -*- coding: utf-8 -*-
import re
from pathlib import Path

t = Path("../Таджикистан.md").read_text(encoding="utf-8")
lines = t.splitlines()


def show(name, hits):
    print("%-28s %d" % (name, len(hits)))
    for ln in hits[:12]:
        print("   L%d: %s" % (lines.index(ln) + 1, ln[:170]))


mixed = [l for l in lines if re.search(r"[А-Яа-яЁё][A-Za-z]|[A-Za-z][А-Яа-яЁё]", re.sub(r"https?://\S+", "", l))]
cjk = [l for l in lines if re.search(r"[一-鿿]", l)]
moj = [l for l in lines if re.search(r"â€|Â|Ð…|Ñ…", l)]
marker = [l for l in lines if "проверено" in l.lower() or "UNCONFIRMED" in l]
latin_in_cyr = []
for l in lines:
    s = re.sub(r"https?://\S+", "", l)
    s = re.sub(r"`[^`]*`", "", s)
    for m in re.finditer(r"[А-Яа-яЁё'’-]*[A-Za-z]{3,}[а-яЁё'’-]*", s):
        w = m.group(0)
        if re.search(r"[А-Яа-я]", w):
            latin_in_cyr.append(l)
            break
domains = [l for l in lines if re.search(
    r"caj\.uz|ufs-online|volago|pph\.tj|volna\.tj|canon\.tj|aviation21|infullbroker|nexign|roadatlas|"
    r"people-pay|ratestats|rahmat\.ru|alif|sutochno|ostrovok|booking|airbnb|somon\.tj|ola\.tj|asiaplus|"
    r"pamirinside|pamirtrips|visitalay|advantour|pressa\.tj|your\.tj|kassa24|x-fit|lifefitness|dorobgym|"
    r"alfa\w*strah|interfax|2gis|mino\.tj|rg\.tj|5shanbe|lalafo|banki\.ru|portali|tour\.tj|vc\.ru|"
    r"Wildberries|IATA|Yandex|Яндекс|Ozon|Суточно|Babilon|ZET|Indigo|B737|A320", l, re.I)]

show("mixed-script", mixed)
show("CJK", cjk)
show("mojibake", moj)
show("latin-inside-cyrillic", latin_in_cyr)
show("marker проверено/UNCONFIRMED", marker)
show("external domains/brands", domains)

print("\nchars %d, lines %d, ## %d, ### %d" % (
    len(t), len(lines), sum(1 for l in lines if l.startswith("## ")),
    sum(1 for l in lines if l.startswith("### "))))
print("links numbered:", sum(1 for l in lines if re.match(r"^\d+\. <", l)))
print("TJS count:", t.count("TJS"))
