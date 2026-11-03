# -*- coding: utf-8 -*-
"""Сжатый просмотр групповой срезки по нескольким фильтрам сразу.

Запуск: python _fold.py <срезка> <выход> <файл_фильтров>
Файл фильтров, строки: имя||группа||вкл||искл||макс_символов||макс_строк
(пустое поле = default). Пишет заголовок фильтра и подходящие строки.
"""
import io
import re
import sys

src, out_path, filt = sys.argv[1], sys.argv[2], sys.argv[3]

groups = {}
cur = None
for line in io.open(src, encoding="utf-8"):
    line = line.rstrip(u"\n")
    if line.startswith(u"====="):
        cur = line.split()[1].rstrip(u":")
        groups.setdefault(cur, [])
        continue
    if line.startswith(u"#") and cur:
        groups[cur].append(line)

out = []
for line in io.open(filt, encoding="utf-8"):
    line = line.rstrip(u"\n")
    if not line.strip() or line.startswith(u"#"):
        continue
    parts = (line.split(u"||") + [u""] * 6)[:6]
    name, grp, inc, exc, ml, cap = parts
    ml = int(ml) if ml else 240
    cap = int(cap) if cap else 60
    rx_in = re.compile(inc, re.I)
    rx_ex = re.compile(exc, re.I) if exc else None
    rows = groups.get(grp, [])
    keep = [r[:ml] for r in rows
            if rx_in.search(r) and not (rx_ex and rx_ex.search(r))]
    if len(keep) > cap:                       # немного ранних + свежие хвосты
        head = cap // 3
        keep = keep[:head] + keep[-(cap - head):]
    out.append(u"\n##### %s (%s, %d/%d)" % (name, grp, len(keep), len(rows)))
    out.extend(keep)

io.open(out_path, "w", encoding="utf-8", newline=u"\n").write(
    u"\n".join(out) + u"\n")
print("written %s" % out_path)
