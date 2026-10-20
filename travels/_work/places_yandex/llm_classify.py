# -*- coding: utf-8 -*-
"""Классифицирует 484 bullet-объекта из _objects.tsv через LLM-эндпоинт
(127.0.0.1:31415/v1, model 'auto') на poi / abstract. Результат —
_classified.tsv: name, label, raw_batch_index. Идемпотентно: дописывает
только недостающие строки; батчи с фатальной ошибкой логируются и
пропускаются (можно перезапустить).
"""
import io
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
IN_TSV = os.path.join(HERE, "_objects.tsv")
OUT_TSV = os.path.join(HERE, "_classified.tsv")
LOG = os.path.join(HERE, "classify.log")

API = "http://127.0.0.1:31415/v1/chat/completions"
KEY = "freellmapi-c50ce86439ddb286b2815f9973fe2c0788ac1f66d6b966e7"
BATCH = 20
MAX_TOK = 8000  # thinking model — needs headroom
RETRIES = 4
SLEEP_BETWEEN = 5


def log(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line.encode("ascii", "replace").decode("ascii"))


def read_names():
    names = []
    with io.open(IN_TSV, encoding="utf-8") as f:
        header = next(f)
        for l in f:
            p = l.rstrip("\n").split("\t")
            if len(p) >= 4 and p[3]:
                names.append(p[3])
    return names


def load_done():
    done = {}
    if not os.path.exists(OUT_TSV):
        return done
    with io.open(OUT_TSV, encoding="utf-8") as f:
        for l in f:
            p = l.rstrip("\n").split("\t")
            if len(p) >= 2:
                done[p[0]] = p[1]
    return done


PROMPT = (
    "You classify Russian-language place names from a Tajikistan travel guide.\n"
    "For each indexed name return exactly one label:\n"
    "  poi — a specific named place / building / street / monument / district that a map service could locate\n"
    "  abstract — a category, style, mood, generic plural ('Проспекты', 'Сталинки', 'Многоэтажки'), or a description of the city's general look (e.g. 'Общий облик', 'Стиль', 'Типовая застройка', 'Архитектура', 'Исторический центр', 'Горы', 'Озёра')\n"
    "Answer STRICTLY as JSON list of [index, label] pairs. No prose. Example for 3 items: [[0,\"abstract\"],[1,\"poi\"],[2,\"poi\"]]\n\n"
    "NAMES:\n%s\n"
)


def call_llm(names_block):
    body = json.dumps({
        "model": "auto",
        "messages": [{"role": "user", "content": PROMPT % names_block}],
        "max_tokens": MAX_TOK,
        "temperature": 0,
    })
    # Use PowerShell via subprocess to avoid Python 3.7 SSL quirks; PS handles UTF-8 well.
    cmd = [
        "powershell", "-NoProfile", "-Command",
        "$ProgressPreference='SilentlyContinue';"
        "$b=[Console]::In.ReadToEnd();"
        "$h=@{Authorization='Bearer %s';'Content-Type'='application/json'};"
        "$r=Invoke-RestMethod -Uri '%s' -Method Post -Headers $h -Body ([Text.Encoding]::UTF8.GetBytes($b)) -TimeoutSec 240;"
        "Write-Output $r.choices[0].message.content" % (KEY, API),
    ]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate(input=body.encode("utf-8"))
    if p.returncode != 0:
        raise RuntimeError("ps rc=%d err=%s" % (p.returncode, err.decode("utf-8", "replace")[:200]))
    return out.decode("utf-8", "replace").strip()


def parse_labels(text, n):
    """Ищем JSON-массив пар [idx,label]; если не парсится — regex по '[[0,"poi"]'."""
    # extract last bracket-balanced JSON array
    m = re.findall(r"\[\s*\[.*?\]\s*\]", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON array in response: %s" % text[:200])
    best = m[-1]
    arr = json.loads(best)
    out = {}
    for pair in arr:
        try:
            idx = int(pair[0])
            lab = str(pair[1]).strip().lower()
        except (TypeError, ValueError):
            continue
        if 0 <= idx < n and lab in ("poi", "abstract"):
            out[idx] = lab
    if not out:
        raise ValueError("empty parse")
    return out


def run_batch(names, start_idx, out_f):
    n = len(names)
    block = "\n".join("%d. %s" % (i, nm) for i, nm in enumerate(names))
    for attempt in range(1, RETRIES + 1):
        t0 = time.time()
        try:
            text = call_llm(block)
            labels = parse_labels(text, n)
            dt = time.time() - t0
            log("batch %d..%d attempt=%d ok in %.1fs parsed=%d/%d"
                % (start_idx, start_idx + n - 1, attempt, dt, len(labels), n))
            for i, nm in enumerate(names):
                lab = labels.get(i, "unknown")
                out_f.write("%s\t%s\t%d\n" % (nm.replace("\t", " ").replace("\n", " "), lab, start_idx + i))
            out_f.flush()
            return True
        except Exception as e:
            dt = time.time() - t0
            log("batch %d..%d attempt=%d FAIL in %.1fs: %s"
                % (start_idx, start_idx + n - 1, attempt, dt, str(e)[:150]))
            time.sleep(15 * attempt)
    return False


def main():
    all_names = read_names()
    done = load_done()
    todo = [(i, nm) for i, nm in enumerate(all_names) if nm not in done]
    log("start: total=%d done=%d todo=%d" % (len(all_names), len(done), len(todo)))
    if not todo:
        log("nothing to do")
        return 0
    with io.open(OUT_TSV, "a", encoding="utf-8") as f:
        # process in BATCH-sized chunks by original index
        i = 0
        while i < len(todo):
            chunk = todo[i:i + BATCH]
            start_idx = chunk[0][0]
            names_only = [nm for _, nm in chunk]
            run_batch(names_only, start_idx, f)
            i += BATCH
            time.sleep(SLEEP_BETWEEN)
    # Summary
    counts = {"poi": 0, "abstract": 0, "unknown": 0}
    if os.path.exists(OUT_TSV):
        for l in io.open(OUT_TSV, encoding="utf-8"):
            p = l.rstrip("\n").split("\t")
            if len(p) >= 2:
                counts[p[1]] = counts.get(p[1], 0) + 1
    log("SUMMARY %s" % json.dumps(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
