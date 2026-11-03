# -*- coding: utf-8 -*-
"""Дамп полных сообщений по номерам из файла фактов, с контекстом диалога.

Запуск: python _src_dump.py <файл_фактов> <выход_файл> [id ...]

Для каждого id печатает: сообщение, на которое дан ответ (полностью), само
сообщение полностью и ответы на него. Нужно, чтобы подбирать дословные цитаты
для раздела — в дампах фактов текст урезан и пересказан.
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MSG = os.path.join(HERE, "messages.jsonl")


def load():
    rows = {}
    kids = {}
    for line in io.open(MSG, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        rid = int(r.get("id") or 0)
        rows[rid] = r
        rt = r.get("reply_to")
        try:
            rt = int(rt)
        except (TypeError, ValueError):
            rt = None
        if rt:
            kids.setdefault(rt, []).append(rid)
    return rows, kids


def show(h, out, rid, rows, kids, tag):
    r = rows.get(rid)
    if r is None:
        out.append(u"### %s #%s MISSING" % (tag, rid))
        return
    txt = re.sub(r"[ \t]+", u" ", (r.get("text") or u"")).strip()
    out.append(u"### %s #%s | %s | %s" % (
        tag, rid, (r.get("date") or u"")[:10], r.get("author") or u""))
    out.append(txt)
    rt = r.get("reply_to")
    try:
        rt = int(rt)
    except (TypeError, ValueError):
        rt = None
    if rt and rt in rows:
        q = re.sub(r"[ \t]+", u" ", (rows[rt].get("text") or u"")).strip()
        out.append(u"    ^ ответ на #%s (%s, %s): %s" % (
            rt, (rows[rt].get("date") or u"")[:10],
            rows[rt].get("author") or u"", q[:700]))
    for k in sorted(kids.get(rid, []))[:4]:
        a = re.sub(r"[ \t]+", u" ", (rows[k].get("text") or u"")).strip()
        out.append(u"    v replies #%s (%s, %s): %s" % (
            k, (rows[k].get("date") or u"")[:10],
            rows[k].get("author") or u"", a[:500]))
    out.append(u"")


def main():
    facts = sys.argv[1]
    out_path = sys.argv[2]
    extra = set(int(x) for x in sys.argv[3:] if x.isdigit())
    ids = []
    for line in io.open(facts, encoding="utf-8"):
        m = re.match(r"\s*#(\d+)", line)
        if m:
            n = int(m.group(1))
            if n not in ids:
                ids.append(n)
    for n in sorted(extra):
        if n not in ids:
            ids.append(n)
    rows, kids = load()
    out = []
    for rid in ids:
        show(u"#", out, rid, rows, kids, u"FACT")
    io.open(out_path, "w", encoding="utf-8", newline=u"\n").write(
        u"\n".join(out) + u"\n")
    print("ids=%d missing=%d -> %s" % (
        len(ids), sum(1 for i in ids if i not in rows),
        os.path.basename(out_path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
