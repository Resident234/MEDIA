# -*- coding: utf-8 -*-
"""Прогнать _work на предмет секретов перед коммитом.

usage: python C:\...\scan_secrets.py   (или из репозитория)

Ищет в travels/_work значения, похожие на живые ключи: сам ключ 2ГИС, любые
UUID-подобные строки, `sk-…`, `Bearer …`, значения api_key=/KEY= с длинным
литералом, и куки-заголовки. Печатает файл:строку и обрезанный фрагмент,
ASCII-escaped (консоль Windows в cp866 падает на кириллице).
"""
import io
import json
import os
import re

ROOT = r"e:\SERVER\Work_MEDIA\travels\_work"
PATTERNS = [
    ("2gis-key", re.compile(r"b82d3fc7\-0219\-43a3\-86a2\-d5baaef7a6be")),
    ("uuid", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)),
    ("sk-token", re.compile(r"\bsk-[A-Za-z0-9\-_]{16,}")),
    ("bearer", re.compile(r"Bearer\s+\S{16,}")),
    ("long-literal-key", re.compile(r"(?:api_?key|apikey|KEY|token)\s*[=:]\s*[\"'][A-Za-z0-9\-_]{20,}[\"']", re.I)),
    ("cookie", re.compile(r"(?:Set-Cookie|Cookie):\s*\S{20,}")),
    ("yandex-session", re.compile(r"[\"'](session?id|_yasc|ypid_)[\"']?\s*[=:]\s*[\"']?[A-Za-z0-9]{20,}")),
]


def main():
    hits = []
    scanned = 0
    for dirpath, _dirs, files in os.walk(ROOT):
        for fn in files:
            p = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(p) > 8 * 1024 * 1024:
                    continue
                raw = io.open(p, "rb").read()
            except (IOError, OSError):
                continue
            if b"\x00" in raw[:2000]:
                continue
            text = raw.decode("utf-8", "replace")
            scanned += 1
            for name, rx in PATTERNS:
                for m in rx.finditer(text):
                    line = text.count("\n", 0, m.start()) + 1
                    frag = text[max(0, m.start() - 30):m.end() + 30].replace("\n", " ")
                    hits.append({"pat": name,
                                 "file": json.dumps(p.replace(ROOT + os.sep, ""), ensure_ascii=True),
                                 "line": line,
                                 "frag": json.dumps(frag, ensure_ascii=True)[:160]})
                    break      # по одному вхождению на паттерн в файле
    print("scanned files: %d, hits: %d" % (scanned, len(hits)))
    for h in hits[:60]:
        print("%-16s %s:%s  %s" % (h["pat"], h["file"], h["line"], h["frag"]))
    return len(hits)


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)
