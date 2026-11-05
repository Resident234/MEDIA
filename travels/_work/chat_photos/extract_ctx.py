# -*- coding: utf-8 -*-
"""Собрать по каждому фото чата: файл, id, дату, автора, подпись и окно
переписки вокруг (контекст), чтобы потом определить сущность на изображении.

Выход: photo_ctx.jsonl (по строке на фото) + сводка в stdout.
"""
import io
import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT = os.path.join(HERE, "..", "..", u"Таджикистан \U0001F1F9\U0001F1EF Чат TravelAsk")
RESULT = os.path.join(EXPORT, "result.json")
OUT = os.path.join(HERE, "photo_ctx.jsonl")

d = json.load(io.open(RESULT, encoding="utf-8"))
msgs = d["messages"]
N = len(msgs)


def txt(m):
    if not isinstance(m, dict):
        return u""
    t = m.get("text")
    if isinstance(t, list):
        t = u" ".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in t)
    return (t or u"").replace(u"\n", u" ").strip()


def clean(s, cap=300):
    s = (s or u"").strip()
    return s[:cap]


rows = []
for i, m in enumerate(msgs):
    if not (isinstance(m, dict) and "photo" in m):
        continue
    before = [txt(msgs[j]) for j in range(max(0, i - 4), i)]
    after = [txt(msgs[j]) for j in range(i + 1, min(N, i + 5))]
    before = [b for b in before if b][-4:]
    after = [a for a in after if a][:4]
    rows.append({
        "id": m.get("id"),
        "date": m.get("date"),
        "author": m.get("from") or m.get("author") or m.get("actor"),
        "file": m.get("photo"),
        "type": m.get("type"),
        "caption": clean(txt(m), 500),
        "ctx_before": [clean(b) for b in before],
        "ctx_after": [clean(a) for a in after],
    })

with io.open(OUT, "w", encoding="utf-8", newline=u"\n") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + u"\n")

# --- сводка ---
with_cap = sum(1 for r in rows if r["caption"])
with_ctx = sum(1 for r in rows if (r["ctx_before"] or r["ctx_after"]))
has_anything = sum(1 for r in rows if r["caption"] or r["ctx_before"] or r["ctx_after"])
print("photo messages      :", len(rows))
print("  with own caption   :", with_cap)
print("  with near context  :", with_ctx)
print("  caption OR context :", has_anything)
print("  NEITHER (blind)    :", len(rows) - has_anything)

# размеры полноразмерных файлов (без _thumb) на диске
photos_dir = os.path.join(EXPORT, "photos")
sizes = Counter()
full = thumb = 0
for fn in os.listdir(photos_dir):
    if fn.endswith("_thumb.jpg"):
        thumb += 1
    elif fn.endswith(".jpg"):
        full += 1
print("disk photos full=%.1f MB  count full=%d thumb=%d"
      % (sum(os.path.getsize(os.path.join(photos_dir, x)) for x in os.listdir(photos_dir)
             if x.endswith(".jpg") and not x.endswith("_thumb.jpg")) / 1048576.0,
         full, thumb))
print("wrote", os.path.basename(OUT))
