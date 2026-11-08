# -*- coding: utf-8 -*-
"""Stage I: применить loc_class.jsonl — разложить природные фото по локациям.

kind=region -> папка канонического кластера; kind=exact -> точное имя
(переиспользуется существующая папка с той же нормой, иначе новая).
Файл перемещается из Прочее; манифест обновляется (stage=loc, category=природа
если пусто); _контекст.md перегенерируются. Идемпотентен.
"""
import csv
import io
import json
import os
import shutil
import sys

from build_folders import safe_folder
from cluster_entities import norm

HERE = os.path.dirname(os.path.abspath(__file__))
TRAVELS = os.path.abspath(os.path.join(HERE, "..", ".."))
ROOT = os.path.join(TRAVELS, u"Фото_сущности")
OTHER = u"Прочее"
LEDGER = os.path.join(HERE, "loc_class.jsonl")
MANIFEST = os.path.join(HERE, "manifest.csv")
GROUPS = os.path.join(HERE, "entity_groups.json")
VISION = os.path.join(HERE, "vision_class.jsonl")


def main():
    if not os.path.exists(LEDGER):
        print("NO_LEDGER")
        return 1
    loc = {}
    for line in io.open(LEDGER, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("named") and (r.get("place") or "").strip():
            loc[int(r["id"])] = r
    if not loc:
        print("NOTHING_LOCATED")
        return 0

    groups = {}
    if os.path.exists(GROUPS):
        groups = json.load(io.open(GROUPS, encoding="utf-8"))
    vcat = {}
    for line in io.open(VISION, encoding="utf-8"):
        try:
            r = json.loads(line)
            vcat[r["id"]] = r.get("category") or u""
        except ValueError:
            pass

    with io.open(MANIFEST, encoding="utf-8-sig", newline=u"") as f:
        rows = list(csv.DictReader(f))
    fieldnames = ["folder", "entity", "category", "stage", "id", "date",
                  "author", "caption", "evidence", "file", "copied"]
    existing_by_norm = {}
    for r in rows:
        existing_by_norm.setdefault(norm(r["folder"]), r["folder"])

    moved = new_dirs = exact_n = region_n = 0
    for r in rows:
        pid = int(r["id"])
        v = loc.get(pid)
        if not v or r["folder"] != OTHER:
            continue
        place = v["place"].strip()
        if v.get("kind") == "region":
            folder = safe_folder(place)
            region_n += 1
        else:
            display = groups.get(norm(place), existing_by_norm.get(norm(place),
                                                                    place))
            folder = safe_folder(display)
            exact_n += 1
        if folder == OTHER or not folder:
            continue
        base = os.path.basename(r["file"])
        src = os.path.join(ROOT, OTHER, base)
        dst_dir = os.path.join(ROOT, folder)
        if not os.path.isdir(dst_dir):
            os.makedirs(dst_dir)
            new_dirs += 1
        dst = os.path.join(dst_dir, base)
        if os.path.exists(src):
            if os.path.exists(dst):
                os.remove(src)
            else:
                shutil.move(src, dst)
                moved += 1
        elif not os.path.exists(dst):
            print("MISSING_BOTH: %s" % base)
            continue
        r["folder"] = folder
        r["entity"] = place
        r["category"] = r["category"] or vcat.get(pid) or u"природа"
        r["stage"] = "loc"
        r["evidence"] = (v.get("evidence") or "")[:160]

    with io.open(MANIFEST, "w", encoding="utf-8-sig", newline=u"\n") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["folder"], int(x["id"]))):
            w.writerow(r)

    prochee_left = sum(1 for r in rows if r["folder"] == OTHER)
    print("LOCATED=%d EXACT=%d REGION=%d MOVED=%d NEW_DIRS=%d PROCHEE_LEFT=%d"
          % (len(loc), exact_n, region_n, moved, new_dirs, prochee_left))

    import write_ctx_md
    write_ctx_md.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
