# -*- coding: utf-8 -*-
"""_route_new.py — по дайджесту _route/<slug>.txt и файлу-назначению печатает
полный текст ТОП-NOT-cited сообщений (те, что ещё не процитированы в разделе).
Формат вывода:  id | DD.MM.YYYY | score | полный текст
Это чистый источник дословных цитат для гейта _verify_8a.py (1.0).
Console ASCII, кириллица только в UTF-8 файлы.
Импорт: python _route_new.py <slug> <target_md> [topN]
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MSGS = os.path.join(HERE, "messages.jsonl")
ROUTE = os.path.join(HERE, "_route", "%s.txt")


def main():
    slug = sys.argv[1]
    target = sys.argv[2]
    topn = int(sys.argv[3]) if len(sys.argv) > 3 else 25
    cited = set(re.findall(r"#(\d+)", io.open(target, encoding="utf-8").read()))
    idx = {}
    for line in io.open(MSGS, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        m = json.loads(line)
        idx[str(m["id"])] = ((m.get("date") or "")[:10],
                             re.sub(r"\s+", " ", m.get("text") or ""))
    out = []
    seen = set()
    for line in io.open(ROUTE % slug, encoding="utf-8"):
        mm = re.match(r"^(\d+) \| (\S+) \| ([\d.]+) \| (.*)$", line.rstrip("\n"))
        if not mm:
            continue
        rid, date, sc, txt = mm.groups()
        if rid in cited or rid in seen:
            continue
        seen.add(rid)
        real_date, real_txt = idx.get(rid, (date, txt))
        out.append(u"%s | %s | %s | %s" % (rid, real_date, sc, real_txt))
        if len(out) >= topn:
            break
    path = os.path.join(HERE, "_route", "%s.new.txt" % slug)
    io.open(path, "w", encoding="utf-8", newline="\n").write(
        u"\n".join(out) + u"\n")
    sys.stdout.write("slug=%s new_not_cited=%d -> _route/%s.new.txt\n"
                     % (slug, len(out), slug))


if __name__ == "__main__":
    main()
