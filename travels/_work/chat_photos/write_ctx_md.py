# -*- coding: utf-8 -*-
"""Stage E: положить в каждую папку Фото_сущности файл _контекст.md.

В файл записывается текстовый контекст из выгрузки чата (TravelAsk),
относящийся к каждому фото папки: подпись фото (caption) и сообщения
до/после него (ctx_before/ctx_after из photo_ctx.jsonl), плюс ссылка-
основание из манифеста, если есть. Идемпотентен: перезаписывает файл
полностью, фото не трогает.

ВНИМАНИЕ: пересборка дерева с CLEAN=1 (build_folders.py) стирает папку
Фото_сущности целиком — после такой пересборки нужно перезапустить этот
скрипт.
"""
import csv
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TRAVELS = os.path.abspath(os.path.join(HERE, "..", ".."))
ROOT = os.path.join(TRAVELS, u"Фото_сущности")
MANIFEST = os.path.join(HERE, "manifest.csv")
PHOTO_CTX = os.path.join(HERE, "photo_ctx.jsonl")
MD_NAME = u"_контекст.md"

H_BEFORE = u"Беседа перед фото"
H_AFTER = u"Беседа после фото"
H_CAPTION = u"Подпись к фото"
H_DATE = u"Дата"
H_AUTHOR = u"Автор"
H_LINK = u"Ссылка-основание"


def load_ctx():
    out = {}
    for line in io.open(PHOTO_CTX, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        out[r["id"]] = r
    return out


def fmt_block(msgs):
    lines = []
    for m in msgs:
        m = (m or u"").strip()
        if m:
            lines.append(u"- " + m.replace(u"\n", u" ").strip())
    return lines


def main():
    ctx = load_ctx()
    by_folder = {}
    with io.open(MANIFEST, encoding="utf-8-sig", newline=u"") as f:
        for r in csv.DictReader(f):
            by_folder.setdefault(r["folder"], []).append(r)

    written = entries = missing_dir = 0
    for folder, rows in sorted(by_folder.items()):
        d = os.path.join(ROOT, folder)
        if not os.path.isdir(d):
            missing_dir += 1
            continue
        lines = [u"# %s" % folder, u""]
        lines.append(u"Text chat context from the TravelAsk export for photos "
                     u"in this folder. / Текстовый контекст чата по фото папки.")
        lines.append(u"")
        for r in sorted(rows, key=lambda x: int(x["id"])):
            p = ctx.get(int(r["id"]))
            if p is None:
                continue
            base = os.path.basename(r["file"])
            lines.append(u"## %s" % base)
            lines.append(u"- %s: %s, %s: %s" % (H_DATE, r.get("date") or u"?",
                                                 H_AUTHOR, r.get("author") or u"?"))
            cap = (p.get("caption") or u"").strip()
            if cap:
                lines.append(u"- %s: %s" % (H_CAPTION, cap))
            before = fmt_block(p.get("ctx_before") or [])
            if before:
                lines.append(u"")
                lines.append(u"### " + H_BEFORE)
                lines.extend(before)
            after = fmt_block(p.get("ctx_after") or [])
            if after:
                lines.append(u"")
                lines.append(u"### " + H_AFTER)
                lines.extend(after)
            link = (r.get("evidence") or u"").strip()
            if link.startswith("http"):
                lines.append(u"- %s: %s" % (H_LINK, link))
            lines.append(u"")
            entries += 1
        with io.open(os.path.join(d, MD_NAME), "w", encoding="utf-8",
                     newline=u"\n") as f:
            f.write(u"\n".join(lines))
        written += 1
    print("MD_WRITTEN=%d PHOTO_ENTRIES=%d FOLDERS_TOTAL=%d MISSING_DIR=%d"
          % (written, entries, len(by_folder), missing_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
