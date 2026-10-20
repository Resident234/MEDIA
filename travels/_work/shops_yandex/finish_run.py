# -*- coding: utf-8 -*-
"""Дожать Яндекс-прогон до конца и собрать всё до конца без человека.

usage: python finish_run.py        (запускать фоном; всё пишется в finish.log)

Идёт поперёк того, что yx_lookup.py ещё работает и что браузерную сессию
`yxshop` нельзя делить с открытием карточек:

1. ждёт, пока в системе не останется ни одного процесса с `yx_lookup.py` в
   командной строке (PID не берётся — он мог переставиться);
2. перезапускает `yx_lookup.py` — прогон возобновляемый: пары с исходом
   `list`/`org`/`empty` пропускаются, `none`/`timeout` пробуются снова,
   добавленные в `_plan.tsv` имена отрабатываются первыми;
3. `parse_rows.py` — all.tsv, cards_input.jsonl, parse_stats.json;
4. `yx_shopcards.py` — открытие приоритетных карточек (сайты, соцсети,
   приложения); оно идёт только после lookup, потому что оба пользуются
   одной сессией `yxshop`;
5. `parse_rows.py` ещё раз (шаг 4 ничего в rows.jsonl не пишет, но пусть будет
   честно — all.tsv пересобирается), `crossmatch_2gis.py`, `make_md.py`,
   `prose_numbers.py` (сверить числа прозы с новыми массивами), а затем
   `build.py` — пересборка Таджикистан.md.

У каждого шага есть потолок времени; если шаг упал или уперся в потолок,
следующий всё равно пробуется — иначе одна заминка обнуляет весь ночной прогон.
"""
import io
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
LOG = os.path.join(HERE, "finish.log")
LOOKUP_WAIT = 6 * 3600        # сколько максимум ждать чужой прогон
LOOKUP_RUN = 5 * 3600         # сколько максимум длиться возобновлённому прогону
CARDS_RUN = 4 * 3600


def note(msg):
    line = "%s %s\n" % (time.strftime("%H:%M:%S"), msg)
    with io.open(LOG, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line)
    sys.stdout.write(line)
    sys.stdout.flush()


def lookups_alive():
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" "
          "| Select-Object -ExpandProperty CommandLine")
    try:
        out = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps])
    except Exception as exc:                       # noqa: BLE001
        note("process probe failed: %r" % (exc,))
        return False
    text = out.decode("utf-8", "replace")
    return any("yx_lookup.py" in l and "finish_run" not in l
               for l in text.splitlines())


def step(name, args, ceiling, tee=None):
    """Запустить шаг, отбить вывод в лог, вернуть код возврата или -1."""
    note("START %s %s" % (name, " ".join(args[1:])))
    started = time.time()
    fh = io.open(os.path.join(HERE, tee or ("%s.out" % name)), "w",
                 encoding="utf-8", newline="\n")
    try:
        proc = subprocess.Popen(args, cwd=HERE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        for raw in proc.stdout:
            fh.write(raw.decode("utf-8", "replace"))
            fh.flush()
            if time.time() - started > ceiling:
                proc.kill()
                note("TIMEOUT %s after %d min" % (name, ceiling // 60))
                return -1
        proc.wait()
        note("END %s rc=%s in %d min" % (name, proc.returncode,
                                         (time.time() - started) // 60))
        return proc.returncode
    except Exception as exc:                       # noqa: BLE001
        note("CRASH %s: %r" % (name, exc))
        return -1
    finally:
        if fh:
            fh.close()


def main():
    note("finish_run started, waiting for the live yx_lookup to end")
    waited = 0
    while lookups_alive():
        time.sleep(120)
        waited += 120
        if waited % 1800 == 0:
            note("still waiting for yx_lookup (%d min)" % (waited // 60))
        if waited > LOOKUP_WAIT:
            note("giving up on the wait after %d min" % (LOOKUP_WAIT // 60))
            break
    note("no live yx_lookup; resuming the plan")

    step("resume_lookup", [PY, "yx_lookup.py"], LOOKUP_RUN, tee="resume_lookup.out")
    step("parse_rows", [PY, "parse_rows.py"], 600, tee="parse_rows.out")
    step("yx_shopcards", [PY, "yx_shopcards.py"], CARDS_RUN, tee="yx_shopcards.out")
    step("parse_rows2", [PY, "parse_rows.py"], 600, tee="parse_rows.out")
    step("crossmatch", [PY, "crossmatch_2gis.py"], 900, tee="crossmatch.out")
    step("make_md", [PY, "make_md.py"], 900, tee="make_md.out")
    # Числа, внесённые в прозу словами, после прогона устаревают; rc=1 здесь
    # означает «текст раздела разошёлся с массивами» (см. prose_numbers.py).
    step("prose_numbers", [PY, "prose_numbers.py"], 300, tee="prose_numbers.out")
    build = subprocess.run([PY, os.path.join(HERE, "..", "build.py")],
                           capture_output=True)
    note("build.py rc=%s %s" % (build.returncode,
                                build.stdout.decode("utf-8", "replace").strip()[:120]))
    note("finish_run done")


if __name__ == "__main__":
    main()
