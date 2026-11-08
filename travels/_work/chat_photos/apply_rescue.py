# -*- coding: utf-8 -*-
"""Stage G: применить rescue_class.jsonl — перенести спасённые фото из 'Прочее'.

Для каждой записи ledger с named=True:
  - known: целевая папка = каноническое имя кандидата (папка уже есть);
  - new: отображаемое имя через entity_groups (та же логика, что build_folders),
    папку при необходимости создаём.
Файл ПЕРЕМЕЩАЕМ из Фото_сущности\\Прочее в целевую папку (подложка-экспорт не
трогаем; если копия в цели уже есть — удаляем дубль из Прочее). Манифест
обновляем (stage=rescue), затем перегенерируем _контекст.md (write_ctx_md).
Идемпотентен: повторный запуск no-op для уже перенесённых.
"""
import csv
import io
import json
import os
import shutil
import sys

from build_folders import safe_folder  # общий фильтр имени папок (импорт без побочек)
from cluster_entities import norm

HERE = os.path.dirname(os.path.abspath(__file__))
TRAVELS = os.path.abspath(os.path.join(HERE, "..", ".."))
ROOT = os.path.join(TRAVELS, u"Фото_сущности")
OTHER = u"Прочее"
LEDGER = os.path.join(HERE, "rescue_class.jsonl")
MANIFEST = os.path.join(HERE, "manifest.csv")
GROUPS = os.path.join(HERE, "entity_groups.json")


def main():
    if not os.path.exists(LEDGER):
        print("NO_LEDGER")
        return 1
    rescued = {}
    for line in io.open(LEDGER, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("named") and (r.get("entity") or "").strip():
            rescued[int(r["id"])] = r
    if not rescued:
        print("NOTHING_RESCUED")
        return 0

    groups = {}
    if os.path.exists(GROUPS):
        groups = json.load(io.open(GROUPS, encoding="utf-8"))

    with io.open(MANIFEST, encoding="utf-8-sig", newline=u"") as f:
        rows = list(csv.DictReader(f))
    fieldnames = ["folder", "entity", "category", "stage", "id", "date",
                  "author", "caption", "evidence", "file", "copied"]

    moved = new_dirs = known_hits = 0
    for r in rows:
        pid = int(r["id"])
        v = rescued.get(pid)
        if not v or r["folder"] != OTHER:
            continue
        if v["source"] == "known":
            folder = safe_folder(v["entity"])
            known_hits += 1
        else:
            display = groups.get(norm(v["entity"]), v["entity"])
            folder = safe_folder(display)
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
                os.remove(src)  # дубль в Прочее убираем
            else:
                shutil.move(src, dst)
                moved += 1
        elif not os.path.exists(dst):
            print("MISSING_BOTH: %s" % base)
            continue
        r["folder"] = folder
        r["entity"] = v["entity"]
        r["category"] = v.get("category") or r["category"]
        r["stage"] = "rescue"
        r["evidence"] = (v.get("evidence") or "")[:160]

    with io.open(MANIFEST, "w", encoding="utf-8-sig", newline=u"\n") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["folder"], int(x["id"]))):
            w.writerow(r)

    prochee_left = sum(1 for r in rows if r["folder"] == OTHER)
    print("RESCUED_TOTAL=%d KNOWN=%d NEW=%d MOVED=%d NEW_DIRS=%d PROCHEE_LEFT=%d"
          % (len(rescued), known_hits, len(rescued) - known_hits, moved,
             new_dirs, prochee_left))

    # перегенерация контекстов во ВСЕХ папках (идемпотентно, секунды)
    import write_ctx_md
    write_ctx_md.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
