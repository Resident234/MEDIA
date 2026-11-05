# -*- coding: utf-8 -*-
"""Stage D: разложить фото по папкам сущностей и собрать манифест.

Порядок выбора папки для фото:
  1) text_class: entity+named  -> папка по каноническому имени;
  2) иначе vision_class: entity+named -> та же логика;
  3) иначе -> 'Прочее'.
Файлы КОПИРУЕМ (подложка-экспорт не трогаем). Служебные фото (type=service)
пропускаем. Манифест: manifest.csv.
"""
import csv
import io
import json
import os
import re
import shutil

from cluster_entities import norm  # та же нормализация

HERE = os.path.dirname(os.path.abspath(__file__))
TRAVELS = os.path.abspath(os.path.join(HERE, "..", ".."))
EXPORT = os.path.join(TRAVELS, u"Таджикистан \U0001F1F9\U0001F1EF Чат TravelAsk")
ROOT = os.path.join(TRAVELS, u"Фото_сущности")
OTHER = u"Прочее"

BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_folder(name):
    s = BAD.sub(u" ", name or u"").strip()
    s = re.sub(r"\s+", u" ", s).strip(u". ")
    return s or OTHER


def load_jsonl(path, key="id"):
    out = {}
    if not os.path.exists(path):
        return out
    for line in io.open(path, encoding="utf-8"):
        try:
            r = json.loads(line)
            out[r[key]] = r
        except (ValueError, KeyError):
            pass
    return out


def main():
    photos = {p["id"]: p for p in
              (json.loads(l) for l in io.open(os.path.join(HERE, "photo_ctx.jsonl"), encoding="utf-8"))}
    texts = load_jsonl(os.path.join(HERE, "text_class.jsonl"))
    vis = load_jsonl(os.path.join(HERE, "vision_class.jsonl"))
    groups_path = os.path.join(HERE, "entity_groups.json")
    groups = json.load(io.open(groups_path, encoding="utf-8")) if os.path.exists(groups_path) else {}

    # CLEAN=1: пересборка с нуля (когда vision переносит фото из Прочее в
    # сущности, иначе в Прочее остаются устаревшие копии). Источник-экспорт
    # не трогаем, всё пересобирается копированием — безопасно.
    if os.environ.get("CLEAN") == "1" and os.path.isdir(ROOT):
        shutil.rmtree(ROOT)

    if not os.path.isdir(ROOT):
        os.makedirs(ROOT)

    rows = []
    copied = named_cnt = other_cnt = skipped_service = 0
    for pid, p in photos.items():
        if p.get("type") == "service":
            skipped_service += 1
            continue
        t = texts.get(pid, {})
        v = vis.get(pid, {})
        entity = stage = category = evidence = u""
        if t.get("named") and (t.get("entity") or "").strip():
            entity, category, evidence, stage = t["entity"], t.get("category", ""), t.get("evidence", ""), "text"
        elif v.get("named") and (v.get("entity") or "").strip():
            entity, category, evidence, stage = v["entity"], v.get("category", ""), v.get("evidence", ""), "vision"
        if entity:
            display = groups.get(norm(entity), entity)
            folder = safe_folder(display)
            named_cnt += 1
        else:
            folder = OTHER
            other_cnt += 1

        src_rel = p["file"]                      # photos/photo_N@date.jpg
        base = os.path.basename(src_rel)
        src = os.path.join(EXPORT, src_rel.replace("photos/", u"photos" + os.sep))
        dst_dir = os.path.join(ROOT, folder)
        if not os.path.isdir(dst_dir):
            os.makedirs(dst_dir)
        dst = os.path.join(dst_dir, base)
        done = False
        if os.path.exists(src):
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
            copied += 1
            done = True
        rows.append({
            "folder": folder, "entity": entity or u"", "category": category or u"",
            "stage": stage or u"", "id": pid, "date": p.get("date") or u"",
            "author": p.get("author") or u"", "caption": (p.get("caption") or u"")[:160],
            "evidence": (evidence or u"")[:160], "file": src_rel,
            "copied": done,
        })

    # манифест
    with io.open(os.path.join(HERE, "manifest.csv"), "w", encoding="utf-8-sig", newline=u"\n") as f:
        w = csv.DictWriter(f, fieldnames=["folder", "entity", "category", "stage", "id",
                                          "date", "author", "caption", "evidence", "file", "copied"])
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["folder"], x["id"])):
            w.writerow(r)

    folders = {}
    for r in rows:
        folders[r["folder"]] = folders.get(r["folder"], 0) + 1
    print("photos (non-service): %d  copied: %d" % (len(rows), copied))
    print("named->entity: %d   Прочее: %d   service skipped: %d"
          % (named_cnt, other_cnt, skipped_service))
    print("folders total: %d (incl. Прочее)" % len(folders))
    print("top folders:")
    for d, c in sorted(folders.items(), key=lambda x: -x[1])[:30]:
        print("  %4d  %s" % (c, d))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
