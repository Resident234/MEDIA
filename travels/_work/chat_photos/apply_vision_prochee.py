# -*- coding: utf-8 -*-
"""Stage L: применить vision_prochee.jsonl к папке Прочее.

accept=exact   -> папка точной сущности (имя прочитано в кадре);
accept=region  -> канонический кластер-регион, НО только для nature=true
                   (ландшафт-догадка; для не-природы регион не считаем
                   достаточным основанием выносить из Прочее);
accept=priroda -> кластер 'Природа' (природа без доступной локации);
остальные       -> остаются в Прочее.
Манифест: folder/entity/stage=vp/category по модели; _контекст.md перегенерируются.
Идемпотентен.
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
LEDGER = os.path.join(HERE, "vision_prochee.jsonl")
MANIFEST = os.path.join(HERE, "manifest.csv")
GROUPS = os.path.join(HERE, "entity_groups.json")


def main():
    if not os.path.exists(LEDGER):
        print("NO_LEDGER")
        return 1
    vp = {}
    for line in io.open(LEDGER, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("accept") in ("exact", "priroda") \
           or (r.get("accept") == "region" and r.get("nature")):
            vp[int(r["id"])] = r
    if not vp:
        print("NOTHING_TO_APPLY")
        return 0

    groups = {}
    if os.path.exists(GROUPS):
        groups = json.load(io.open(GROUPS, encoding="utf-8"))
    with io.open(MANIFEST, encoding="utf-8-sig", newline=u"") as f:
        rows = list(csv.DictReader(f))
    fieldnames = ["folder", "entity", "category", "stage", "id", "date",
                  "author", "caption", "evidence", "file", "copied"]
    existing_by_norm = {}
    for r in rows:
        existing_by_norm.setdefault(norm(r["folder"]), r["folder"])

    moved = {"exact": 0, "region": 0, "priroda": 0}
    for r in rows:
        pid = int(r["id"])
        v = vp.get(pid)
        if not v or r["folder"] != OTHER:
            continue
        accept = v["accept"]
        if accept == u"region":
            folder = safe_folder(v["place"])
        elif accept == u"exact":
            display = groups.get(norm(v["place"]),
                                 existing_by_norm.get(norm(v["place"]),
                                                      v["place"]))
            folder = safe_folder(display)
        else:
            folder = u"Природа"
        if folder == OTHER or not folder:
            continue
        base = os.path.basename(r["file"])
        src = os.path.join(ROOT, OTHER, base)
        dst_dir = os.path.join(ROOT, folder)
        if not os.path.isdir(dst_dir):
            os.makedirs(dst_dir)
        dst = os.path.join(dst_dir, base)
        if os.path.exists(src):
            if os.path.exists(dst):
                os.remove(src)
            else:
                shutil.move(src, dst)
        elif not os.path.exists(dst):
            print("MISSING_BOTH: %s" % base)
            continue
        r["folder"] = folder
        if v.get("place"):
            r["entity"] = v["place"]
        r["category"] = v.get("category") or r["category"]
        r["stage"] = "vp"
        r["evidence"] = (u"vision: " + (v.get("evidence") or u""))[:160]
        moved[accept] += 1

    with io.open(MANIFEST, "w", encoding="utf-8-sig", newline=u"\n") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["folder"], int(x["id"]))):
            w.writerow(r)

    prochee_left = sum(1 for r in rows if r["folder"] == OTHER)
    print("APPLIED exact=%d region=%d priroda=%d PROCHEE_LEFT=%d"
          % (moved["exact"], moved["region"], moved["priroda"], prochee_left))

    import write_ctx_md
    write_ctx_md.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
