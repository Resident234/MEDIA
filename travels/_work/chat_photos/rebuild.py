# -*- coding: utf-8 -*-
"""Оркестратор пересборки папок после фоновой vision-классификации.

Идемпотентен: считает число vision-записей с собственным именем; если оно не
выросло с прошлого запуска — ничего не делает (дешёвый no-op для планировщика).
Иначе: Stage C (cluster, уже с vision-именами) -> Stage D (build, CLEAN=1,
пересборка дерева с нуля, чтобы в 'Прочее' не оставалось устаревших копий).

В конце печатает строку REBUILT=<да/нет> NAMED_VISION=<n> FOLDERS=<f>
PROCHEE=<p> — по ней агент/человек решает, делать ли коммит.
"""
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "vision_class.jsonl")
MARKER = os.path.join(HERE, "_last_rebuild.json")
MANIFEST = os.path.join(HERE, "manifest.csv")


def named_vision_count():
    if not os.path.exists(LEDGER):
        return 0
    c = 0
    for line in io.open(LEDGER, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("named") and (r.get("entity") or "").strip():
            c += 1
    return c


def read_marker():
    if os.path.exists(MARKER):
        try:
            return json.load(io.open(MARKER, encoding="utf-8")).get("named_vision", -1)
        except ValueError:
            return -1
    return -1


def run(script, env_extra=None):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("LLM_MODELS", "gpt-oss-20b,auto,fusion")
    if env_extra:
        env.update(env_extra)
    print(">>", script, env_extra or "")
    p = subprocess.call([sys.executable, "-u", script], cwd=HERE, env=env)
    if p != 0:
        raise SystemExit("%s failed rc=%d" % (script, p))


def summarize():
    import csv
    folders = 0
    prochee = 0
    if os.path.exists(MANIFEST):
        with io.open(MANIFEST, encoding="utf-8-sig", newline="") as f:
            seen = set()
            for r in csv.DictReader(f):
                seen.add(r["folder"])
                if r["folder"] == u"Прочее":
                    prochee += 1
            folders = len(seen)
    return folders, prochee


def main():
    n = named_vision_count()
    last = read_marker()
    if n == 0 or n <= last:
        print("REBUILT=no NAMED_VISION=%d (marker=%d) — новых vision-имён нет" % (n, last))
        return 0
    run("cluster_entities.py")
    run("build_folders.py", {"CLEAN": "1"})
    folders, prochee = summarize()
    io.open(MARKER, "w", encoding="utf-8").write(
        json.dumps({"named_vision": n}, ensure_ascii=False))
    print("REBUILT=yes NAMED_VISION=%d FOLDERS=%d PROCHEE=%d" % (n, folders, prochee))
    return 0


if __name__ == "__main__":
    sys.exit(main())
