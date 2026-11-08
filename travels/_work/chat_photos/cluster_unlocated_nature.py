# -*- coding: utf-8 -*-
"""Stage J: нелокализованные природные фото -> кластер 'Природа'.

Берёт строки манифеста, лежащие в Прочее, чья итоговая категория
(rescue_class -> vision_class) = "природа" и которые так и не получили
локацию (их уже перенесли Stage I). Перемещает файлы в папку 'Природа',
обновляет манифест (folder=Природа, stage=unloc), перегенерирует _контекст.md.
Идемпотентен.
"""
import csv
import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TRAVELS = os.path.abspath(os.path.join(HERE, "..", ".."))
ROOT = os.path.join(TRAVELS, u"Фото_сущности")
OTHER = u"Прочее"
DST = u"Природа"
MANIFEST = os.path.join(HERE, "manifest.csv")


def cat_ledger(path):
    d = {}
    if os.path.exists(path):
        for l in io.open(path, encoding="utf-8"):
            try:
                r = json.loads(l)
                d[r["id"]] = r.get("category") or u""
            except ValueError:
                pass
    return d


def main():
    rc = cat_ledger(os.path.join(HERE, "rescue_class.jsonl"))
    vc = cat_ledger(os.path.join(HERE, "vision_class.jsonl"))
    with io.open(MANIFEST, encoding="utf-8-sig", newline=u"") as f:
        rows = list(csv.DictReader(f))
    fieldnames = ["folder", "entity", "category", "stage", "id", "date",
                  "author", "caption", "evidence", "file", "copied"]

    dst_dir = os.path.join(ROOT, DST)
    if not os.path.isdir(dst_dir):
        os.makedirs(dst_dir)

    moved = 0
    for r in rows:
        if r["folder"] != OTHER:
            continue
        pid = int(r["id"])
        if (rc.get(pid) or vc.get(pid)) != u"природа":
            continue
        base = os.path.basename(r["file"])
        src = os.path.join(ROOT, OTHER, base)
        dst = os.path.join(dst_dir, base)
        if os.path.exists(src):
            if not os.path.exists(dst):
                shutil.move(src, dst)
            else:
                os.remove(src)
        elif not os.path.exists(dst):
            print("MISSING_BOTH: %s" % base)
            continue
        r["folder"] = DST
        r["category"] = u"природа"
        r["stage"] = "unloc"
        moved += 1

    with io.open(MANIFEST, "w", encoding="utf-8-sig", newline=u"\n") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["folder"], int(x["id"]))):
            w.writerow(r)

    prochee_left = sum(1 for r in rows if r["folder"] == OTHER)
    print("MOVED=%d TO '%s' PROCHEE_LEFT=%d" % (moved, DST, prochee_left))

    import write_ctx_md
    write_ctx_md.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
