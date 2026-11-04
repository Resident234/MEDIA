# -*- coding: utf-8 -*-
"""Вынести технические детали сбора данных из путеводителя в отдельный файл.

usage: python extract_tech.py [--dry]

В путеводителе остаются только сами данные и практические выводы. Всё, что
описывает *как* и *когда* снимали массивы — строки «_Источник: …, съём …_»,
подразделы «Как собрано…», «Итог запроса…», «Что осталось незакрытым»,
методологические абзацы про разбор чата и LLM-разметку — вырезается из
`build/*.md` и переносится в `travels/Таджикистан_техника_сбора.md`.

Скрипт идемпотентен: повторный запуск ничего не вырезает второй раз, а
тех-file пересобирается с нуля. Вызывается из build.py после сборки частей,
поэтому блоки, перегенерированные make_md.py, очищаются автоматически.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, "build")
OUT = os.path.join(HERE, os.pardir,
                   u"\u0422\u0430\u0434\u0436\u0438\u043a\u0438\u0441\u0442\u0430\u043d_"
                   u"\u0442\u0435\u0445\u043d\u0438\u043a\u0430_\u0441\u0431\u043e\u0440\u0430.md")

# Как подписывать вырезанное в тех-файле: файл -> ("номер части", "подзаголовок").
PARTS = {
    "00_head.md":          (u"\u041e\u0433\u043b\u0430\u0432\u043b\u0435\u043d\u0438\u0435", u"\u041f\u0440\u043e\u0438\u0441\u0445\u043e\u0436\u0434\u0435\u043d\u0438\u0435 \u043c\u0430\u0441\u0441\u0438\u0432\u0430"),
    "10_viza.md":          (u"1. \u0412\u0438\u0437\u0430 \u0438 \u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u044f", None),
    "15_tamozhnya.md":     (u"1a. \u0422\u0430\u043c\u043e\u0436\u043d\u044f", None),
    "16_granitsa.md":      (u"1b. \u0413\u0440\u0430\u043d\u0438\u0446\u0430 \u0438 \u041a\u041f\u041f", None),
    "20_zhile.md":         (u"2. \u0416\u0438\u043b\u044c\u0451", None),
    "30_dengi.md":         (u"3. \u0414\u0435\u043d\u044c\u0433\u0438 \u0438 \u0431\u0430\u043d\u043a\u0438", None),
    "40_transport.md":     (u"4. \u0422\u0440\u0430\u043d\u0441\u043f\u043e\u0440\u0442", None),
    "45_svyaz.md":         (u"5. \u0421\u0432\u044f\u0437\u044c \u0438 \u0438\u043d\u0442\u0435\u0440\u043d\u0435\u0442", None),
    "50_places_intro.md":  (u"6. \u041c\u0435\u0441\u0442\u0430", None),
    "60_eda.md":           (u"7. \u0415\u0434\u0430 \u0438 \u0437\u0430\u0432\u0435\u0434\u0435\u043d\u0438\u044f", None),
    "61_eda_city.md":      (u"7. \u0415\u0434\u0430 \u2014 \u043f\u043e \u0433\u043e\u0440\u043e\u0434\u0430\u043c", None),
    "62_alc.md":           (u"7c. \u0410\u043b\u043a\u043e\u0433\u043e\u043b\u044c", None),
    "70_pokupki.md":       (u"8. \u041f\u043e\u043a\u0443\u043f\u043a\u0438 \u0438 \u043a\u0430\u0440\u0442\u044b", None),
    "71_pokupki_chat.md":  (u"8. \u041f\u043e\u043a\u0443\u043f\u043a\u0438 \u2014 \u0447\u0430\u0442", None),
    "73_dostavka.md":      (u"8d. \u0417\u0430\u043a\u0430\u0437\u044b \u0438 \u043f\u043e\u0441\u044b\u043b\u043a\u0438", None),
    "80_prochee.md":       (u"9. \u041f\u0440\u043e\u0447\u0435\u0435", None),
    "81_prochee_chat.md":  (u"9. \u041f\u0440\u043e\u0447\u0435\u0435 \u2014 \u0447\u0430\u0442", None),
    "85_fitness.md":       (u"10. \u0422\u0440\u0435\u043d\u0430\u0436\u0451\u0440\u043d\u044b\u0435 \u0437\u0430\u043b\u044b", None),
    "86_fitness_chat.md":  (u"10. \u0417\u0430\u043b\u044b \u2014 \u0447\u0430\u0442", None),
    "90_med.md":           (u"11. \u041c\u0435\u0434\u0438\u0446\u0438\u043d\u0430", None),
    "91_med_chat.md":      (u"11. \u041c\u0435\u0434\u0438\u0446\u0438\u043d\u0430 \u2014 \u0447\u0430\u0442", None),
    "92_seks.md":          (u"12. \u0421\u0435\u043a\u0441-\u0448\u043e\u043f\u044b", None),
    "93_dating.md":        (u"13. \u0417\u043d\u0430\u043a\u043e\u043c\u0441\u0442\u0432\u0430", None),
    "95_zametki.md":       (u"14. \u0417\u0430\u043c\u0435\u0442\u043a\u0438 \u2014 \u0441\u0442\u0430\u0442\u0443\u0441\u044b", None),
    "99_links_intro.md":   (u"\u041e\u0431\u0440\u0430\u0431\u043e\u0442\u0430\u043d\u043d\u044b\u0435 \u0441\u0441\u044b\u043b\u043a\u0438", None),
}

# Однострочные курсивные заметки о съёме внутри генерируемых блоков.
SCAN_KW = (
    u"\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a",   # Источник
    u"\u0441\u044a\u0451\u043c",                     # съём
    u"\u041f\u043e \u0434\u0430\u043d\u043d\u044b\u043c",  # По данным
    u"agent-browser",
    u"Places API",
)

# Префиксы абзацев, которые вырезаются целиком (один абзац, до пустой строки).
PROSE_PREFIXES = (
    u"**\u0427\u0442\u043e \u0437\u0434\u0435\u0441\u044c \u0435\u0441\u0442\u044c \u0438 \u0447\u0435\u0433\u043e \u043d\u0435\u0442.**",
    u"**\u0427\u0442\u043e \u0437\u0434\u0435\u0441\u044c \u043f\u043e\u044f\u0432\u0438\u043b\u043e\u0441\u044c",
    u"**\u0427\u0442\u043e \u044d\u0442\u043e \u0437\u0430 \u0431\u043b\u043e\u043a \u0438 \u0447\u0435\u0433\u043e \u0432 \u043d\u0451\u043c \u043d\u0435\u0442.**",
    u"**\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a \u044d\u0442\u043e\u0433\u043e",
    u"**\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a \u0432\u0441\u0435\u0445 \u0444\u0430\u043a\u0442\u043e\u0432.**",
    u"**\u041f\u0440\u043e\u0438\u0441\u0445\u043e\u0436\u0434\u0435\u043d\u0438\u0435 \u043c\u0430\u0441\u0441\u0438\u0432\u0430.**",
    u"**\u041f\u0440\u043e\u0438\u0441\u0445\u043e\u0436\u0434\u0435\u043d\u0438\u0435 \u0434\u0430\u043d\u043d\u044b\u0445.**",
    u"\u0421\u043e\u0431\u0440\u0430\u043d \u0438\u0437 73 \u0441\u0441\u044b\u043b\u043e\u043a",  # 00_head intro
)

# Подразделы (заголовок любого уровня), уносящиеся целиком вместе с телом.
# Тело = строки до заголовка того же или более высокого уровня ИЛИ до HTML-
# комментария `<!-- XXX_END ... -->` (границы генерируемых блоков).
HEADING_EXACT = {
    u"### \u041a\u0430\u043a \u0441\u043e\u0431\u0440\u0430\u043d\u043e, \u0447\u0442\u043e\u0431\u044b \u043c\u043e\u0436\u043d\u043e \u0431\u044b\u043b\u043e \u043f\u0435\u0440\u0435\u043f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c",
    u"### \u041a\u0430\u043a \u0441\u043e\u0431\u0440\u0430\u043d\u0430 \u044d\u0442\u0430 \u0447\u0430\u0441\u0442\u044c \u0438 \u0447\u0442\u043e \u043e\u043d\u0430 \u043f\u043e\u043a\u0440\u044b\u0432\u0430\u0435\u0442 (\u0441\u0432\u043e\u0434\u043a\u0430 \u0441\u0431\u043e\u0440\u0449\u0438\u043a\u0430)",
    u"### \u0427\u0442\u043e \u043e\u0441\u0442\u0430\u043b\u043e\u0441\u044c \u043d\u0435\u0437\u0430\u043a\u0440\u044b\u0442\u044b\u043c",
    u"### \u0427\u0442\u043e \u043e\u0441\u0442\u0430\u043b\u043e\u0441\u044c \u043d\u0435\u0437\u0430\u043a\u0440\u044b\u0442\u044b\u043c \u0438 \u0447\u0442\u043e \u0434\u043b\u044f \u044d\u0442\u043e\u0433\u043e \u043d\u0443\u0436\u043d\u043e",
    u"### \u0421\u0432\u0435\u0440\u043a\u0430 \u0434\u0432\u0443\u0445 \u0441\u043f\u0440\u0430\u0432\u043e\u0447\u043d\u0438\u043a\u043e\u0432",
    u"### \u041c\u0430\u0441\u0441\u0438\u0432\u044b, \u0438\u0437 \u043a\u043e\u0442\u043e\u0440\u044b\u0445 \u0441\u043e\u0431\u0440\u0430\u043d \u044d\u0442\u043e\u0442 \u0431\u043b\u043e\u043a",
    u"### 2\u0413\u0418\u0421 \u0437\u043d\u0430\u0435\u0442 \u0432 \u0422\u0430\u0434\u0436\u0438\u043a\u0438\u0441\u0442\u0430\u043d\u0435 \u0442\u043e\u043b\u044c\u043a\u043e \u0414\u0443\u0448\u0430\u043d\u0431\u0435",
    u"### \u042f\u043d\u0434\u0435\u043a\u0441.\u041a\u0430\u0440\u0442\u044b: \u0447\u0435\u043c \u043f\u043e\u043a\u0440\u044b\u0442\u0430 \u0441\u0442\u0440\u0430\u043d\u0430 \u0438 \u0447\u0435\u043c \u043d\u0435 \u043f\u043e\u043a\u0440\u044b\u0442\u0430",
    u"#### \u041a\u0430\u043a \u043e\u0442\u0431\u0438\u0440\u0430\u043b\u0438\u0441\u044c \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f \u0438 \u0447\u0442\u043e \u043f\u043e\u043a\u0430\u0437\u0430\u043b\u0430 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u043c\u043e\u0434\u0435\u043b\u044c\u044e",
    u"#### \u041a\u0430\u043a \u044d\u0442\u043e \u0441\u043e\u0431\u0438\u0440\u0430\u043b\u043e\u0441\u044c \u0438 \u043f\u0440\u043e\u0432\u0435\u0440\u044f\u043b\u043e\u0441\u044c",
    u"### \u0418\u0442\u043e\u0433 \u0437\u0430\u043f\u0440\u043e\u0441\u0430",
    u"### \u0418\u0442\u043e\u0433 \u0437\u0430\u043f\u0440\u043e\u0441\u0430: \u0447\u0442\u043e \u0437\u0430\u043a\u0440\u044b\u0442\u043e, \u0447\u0442\u043e \u043d\u0435\u0442",
    u"### \u0412\u044b\u0431\u043e\u0440\u043a\u0430 \u0432 \u0446\u0438\u0444\u0440\u0430\u0445",
    u"### \u042f\u043d\u0434\u0435\u043a\u0441.\u041a\u0430\u0440\u0442\u044b \u2014 \u0442\u0435 \u0436\u0435 \u0434\u0432\u0430 \u0437\u0430\u043f\u0440\u043e\u0441\u0430",
}

# Отдельные bullet-строки, вырезаемые по точному вхождению подстроки.
BULLET_SUBSTR = (
    u"\u041f\u043e\u0434\u0440\u0430\u0437\u0434\u0435\u043b \u00ab\u0427\u0430\u0442 TravelAsk\u00bb \u0441\u043e\u0431\u0440\u0430\u043d \u043d\u0435 \u0438\u0437 \u0441\u0442\u0430\u0442\u0435\u0439",
    u"\u041a\u0430\u043a \u043f\u0440\u043e\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u044b \u0441\u0441\u044b\u043b\u043a\u0438",  # 00_head
)

# Хвосты абзацев, которые переносятся целиком. Формат: (file, needle_start).
SURGICAL = [
    (u"16_granitsa.md",
     u"\u041c\u0430\u0442\u0435\u0440\u0438\u0430\u043b \u2014 \u0442\u043e\u0442 \u0436\u0435 \u0437\u0430\u043a\u0440\u044b\u0442\u044b\u0439 \u0447\u0430\u0442"),
    (u"73_dostavka.md",
     u"\u041f\u043e\u044d\u0442\u043e\u043c\u0443 \u0432\u0435\u0441\u044c \u0440\u0430\u0477\u0434\u0435\u043b \u043f\u043e\u0441\u0442\u0440\u043e\u0435\u043d \u043d\u0430 \u0447\u0430\u0442\u0435"),
    (u"93_dating.md",
     u"\u042d\u0442\u043e \u043d\u0435 \u0447\u0430\u0442 \u0437\u043d\u0430\u043a\u043e\u043c\u0441\u0442\u0432, \u0430 \u0447\u0430\u0442 \u0442\u0443\u0440\u0438\u0441\u0442\u0438\u0447\u0435\u0441\u043a\u043e\u0439"),
    (u"92_seks.md",
     u"\u0422\u0435\u043c\u0430 \u0432 \u043d\u0451\u043c \u043f\u043e\u0447\u0442\u0438 \u043d\u0435 \u043e\u0431\u0441\u0443\u0436\u0434\u0430\u0435\u0442\u0441\u044f"),
    (u"20_zhile.md",
     u"\u042d\u0442\u043e \u043d\u0435 \u0441\u043f\u0440\u0430\u0432\u043e\u0447\u043d\u0438\u043a: \u043e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u043f\u043e\u0442\u043e\u043a"),
]

DRY = "--dry" in sys.argv


def read(name):
    return io.open(os.path.join(W, name), encoding="utf-8").read()


def write(name, text):
    io.open(os.path.join(W, name), "w", encoding="utf-8",
            newline="\n").write(text)


def heading_level(line):
    if not line.startswith("#"):
        return 0
    n = 0
    for ch in line:
        if ch == "#":
            n += 1
        else:
            break
    return n if n <= 6 and (len(line) == n or line[n] == " ") else 0


def is_boundary_block_end(line):
    """`<!-- XXX_END -->` or `<!-- XXX_BLOCK_END -->` — конец генерируемого блока."""
    s = line.strip()
    if not s.startswith("<!--"):
        return False
    body = s[4:].split("-->")[0].strip().upper()
    return "END" in body


def cut_paragraph(lines, start):
    """Вырезать строки paragraphs[start] до пустой строки или границы."""
    end = start + 1
    while end < len(lines) and lines[end].strip():
        if heading_level(lines[end]) > 0 or lines[end].lstrip().startswith("<!--"):
            break
        end += 1
    body = lines[start:end]
    del lines[start:end]
    # захватить и последующую пустую строку, если она есть, чтобы не оставлять двойной разрыв
    if start < len(lines) and not lines[start].strip():
        del lines[start]
    return body


def cut_block_same_level(lines, start):
    """Вырезать заголовок и его тело до заголовка того же или более высокого уровня
    либо до `<!-- *_END -->` (конец генерируемого блока)."""
    lvl = heading_level(lines[start])
    end = start + 1
    while end < len(lines):
        h = heading_level(lines[end])
        if h and h <= lvl:
            break
        if is_boundary_block_end(lines[end]):
            break
        end += 1
    body = lines[start:end]
    del lines[start:end]
    if start < len(lines) and not lines[start].strip():
        del lines[start]
    return body


def trim(body):
    while body and not body[-1].strip():
        body.pop()
    while body and not body[0].strip():
        body.pop(0)
    return body


# ------------------------------------------------------------------- actions
def extract_prose(name):
    """Целиком абзацы, начинающиеся с про-отчётного префикса."""
    lines = read(name).split("\n")
    moved = []
    k = 0
    while k < len(lines):
        s = lines[k]
        if s.startswith(PROSE_PREFIXES):
            title = s[:60].strip()
            moved.append((title, trim(cut_paragraph(lines, k))))
            continue
        for b in BULLET_SUBSTR:
            if s.startswith("- ") and b in s:
                body = [lines.pop(k)]
                while k < len(lines) and lines[k].startswith("  "):
                    body.append(lines.pop(k))
                moved.append((u"\u041e\u0433\u043e\u0432\u043e\u0440\u043a\u0430", trim(body)))
                break
        k += 1
    if moved and not DRY:
        write(name, "\n".join(lines))
    return moved


def extract_headings(name):
    """Вырезание подразделов по HEADING_EXACT."""
    lines = read(name).split("\n")
    moved = []
    changed = True
    while changed:
        changed = False
        for k, line in enumerate(lines):
            want = line.strip()
            if want in HEADING_EXACT:
                moved.append((want, trim(cut_block_same_level(lines, k))))
                changed = True
                break
    if moved and not DRY:
        write(name, "\n".join(lines))
    return moved


def extract_scan(name):
    """Однострочные курсивные заметки о съёме (перегенерируются make_md)."""
    lines = read(name).split("\n")
    moved = []
    k = 0
    while k < len(lines):
        s = lines[k].strip()
        if (len(s) > 3 and s.startswith("_") and s.endswith("_")
                and not s.startswith("_*")
                and any(w in s for w in SCAN_KW)):
            moved.append((u"\u0417\u0430\u043c\u0435\u0442\u043a\u0430 \u043e \u0441\u044a\u0451\u043c\u0435",
                          [lines.pop(k)]))
            # убрать пустую строку перед/после, чтобы не оставить двойной разрыв
            if k < len(lines) and not lines[k].strip():
                del lines[k]
            elif k > 0 and not lines[k - 1].strip() and (k >= len(lines) or not lines[k].strip()):
                del lines[k - 1]
                k -= 1
            continue
        k += 1
    if moved and not DRY:
        write(name, "\n".join(lines))
    return moved


def cut_tail_sentence(name, needle):
    """Перенести хвост абзаца, начинающийся с `needle`, целиком."""
    text = read(name)
    i = text.find(needle)
    if i < 0:
        return None
    # найти границу абзаца: две подряд \n
    j = text.find("\n\n", i)
    para = text[i:j] if j > 0 else text[i:]
    if not DRY:
        # вырезать para из text и убрать пустую строку перед ним
        new = text[:i] + text[j:]
        write(name, new)
    return para.strip()


def fix_legend_counts():
    """В 00_head.md легенда про метки [→N] содержит длинный перечёт типов
    строк без ссылок — сократить до одной нейтральной формулировки, не трогая
    остальную часть bullet."""
    name = u"00_head.md"
    text = read(name)
    old_key = u"\u0421\u0441\u044b\u043b\u043e\u043a \u043d\u0435\u0442 \u0442\u043e\u043b\u044c\u043a\u043e \u0443 \u043f\u044f\u0442\u0438 \u0442\u0438\u043f\u043e\u0432 \u0441\u0442\u0440\u043e\u043a"
    if old_key not in text:
        return False
    i = text.find(old_key)
    j = text.find("\n", i)
    if j < 0:
        return False
    tail = (u"\u0421\u0441\u044b\u043b\u043e\u043a \u043d\u0435\u0442 \u0442\u043e\u043b\u044c\u043a\u043e "
            u"\u0443 \u0441\u0442\u0440\u043e\u043a, \u043a\u043e\u0442\u043e\u0440\u044b\u0435 "
            u"\u043d\u0435 \u0441\u043e\u043e\u0431\u0449\u0430\u044e\u0442 \u0444\u0430\u043a\u0442: "
            u"\u043f\u043e\u0434\u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043a\u0438 \u0438 \u043f\u043e\u0434\u0432\u043e\u0434\u043a\u0438, "
            u"\u0441\u043b\u0443\u0436\u0435\u0431\u043d\u044b\u0435 \u0441\u0442\u0440\u043e\u043a\u0438, "
            u"\u043d\u0430\u0432\u0438\u0433\u0430\u0446\u0438\u044f \u0438 \u0432\u044b\u0432\u043e\u0434\u044b \u043f\u043e "
            u"\u043c\u0430\u0441\u0441\u0438\u0432\u0443 \u2014 \u0430 \u0442\u0430\u043a\u0436\u0435 \u0443 "
            u"\u0441\u0442\u0440\u043e\u043a \u0440\u0430\u0437\u0434\u0435\u043b\u0430 10, \u0433\u0434\u0435 "
            u"\u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a \u2014 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0430 "
            u"2\u0413\u0418\u0421 \u0438\u043b\u0438 \u042f\u043d\u0434\u0435\u043a\u0441.\u041a\u0430\u0440\u0442, "
            u"\u0430 \u043d\u0435 \u0441\u0442\u0430\u0442\u044c\u044f.")
    text = text[:i] + tail + text[j:]
    if not DRY:
        write(name, text)
    return True


# ------------------------------------------------------------------- emit
def norm(text):
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


HEADER_TPL = (
    u"# \u0422\u0430\u0434\u0436\u0438\u043a\u0438\u0441\u0442\u0430\u043d \u2014 \u0442\u0435\u0445\u043d\u0438\u043a\u0430 \u0441\u0431\u043e\u0440\u0430 \u0434\u0430\u043d\u043d\u044b\u0445\n"
    u"\n"
    u"\u0421\u043b\u0443\u0436\u0435\u0431\u043d\u044b\u0439 \u0441\u043b\u043e\u0439 \u043f\u0443\u0442\u0435\u0432\u043e\u0434\u0438\u0442\u0435\u043b\u044f: \u0437\u0434\u0435\u0441\u044c \u0441\u043e\u0431\u0440\u0430\u043d\u043e \u0432\u0441\u0451, \u043a\u0430\u043a \u0438 \u043a\u043e\u0433\u0434\u0430 \u0441\u043d\u0438\u043c\u0430\u043b\u0438\u0441\u044c \u043c\u0430\u0441\u0441\u0438\u0432\u044b \u2014 \u043a\u0430\u043d\u0430\u043b\u044b, \u0437\u0430\u043f\u0440\u043e\u0441\u044b, \u043f\u0440\u043e\u0433\u043e\u043d\u044b, \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438 \u0438 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f. \u0412 \u0441\u0430\u043c\u043e\u043c \u043f\u0443\u0442\u0435\u0432\u043e\u0434\u0438\u0442\u0435\u043b\u0435 \u044d\u0442\u0438 \u0441\u0432\u0435\u0434\u0435\u043d\u0438\u044f \u043d\u0435 \u0432\u0435\u0434\u0443\u0442: \u043e\u043d\u0438 \u043d\u0443\u0436\u043d\u044b \u0442\u043e\u043b\u044c\u043a\u043e \u043f\u0440\u0438 \u043f\u0435\u0440\u0435\u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0435 \u0438\u043b\u0438 \u0434\u043e\u0431\u043e\u0440\u0435 \u0434\u0430\u043d\u043d\u044b\u0445.\n"
    u"\n"
    u"\u0424\u0430\u0439\u043b \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u043f\u0435\u0440\u0435\u0441\u043e\u0431\u0438\u0440\u0430\u0435\u0442\u0441\u044f \u0441\u043a\u0440\u0438\u043f\u0442\u043e\u043c `_work/extract_tech.py` \u043f\u0440\u0438 \u043a\u0430\u0436\u0434\u043e\u043c \u043f\u0440\u043e\u0433\u043e\u043d\u0435 `build.py`.\n"
    u"\n"
)


def emit(buckets):
    parts = []
    order = [n for n in sorted(PARTS) if n in buckets]
    for name in order:
        label, sub = PARTS[name]
        head = u"## %s" % label
        if sub:
            head += u" \u2014 %s" % sub
        parts.append(head + u"\n")
        for title, text in buckets[name]:
            parts.append(u"### %s\n\n%s\n" % (title, text))
    body = u"\n".join(parts)
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(
        norm(HEADER_TPL + u"\n" + body))


def main():
    buckets = {}

    def add(fname, title, body_lines):
        text = "\n".join(body_lines).strip()
        if not text:
            return
        buckets.setdefault(fname, []).append((title, text))

    touched = []
    for name in sorted(PARTS):
        path = os.path.join(W, name)
        if not os.path.exists(path):
            continue
        before = read(name)
        got = []
        got += extract_prose(name)
        got += extract_headings(name)
        got += extract_scan(name)
        for title, body in got:
            add(name, title, body)
        if read(name) != before:
            touched.append(name)

    # точечные правки хвостов абзацев (после сплошных вырезаний)
    for name, needle in SURGICAL:
        moved = cut_tail_sentence(name, needle)
        if moved:
            add(name, u"\u041f\u0440\u043e\u0438\u0441\u0445\u043e\u0436\u0434\u0435\u043d\u0438\u0435 \u0434\u0430\u043d\u043d\u044b\u0445: `%s`" % name, [moved])
            if name not in touched:
                touched.append(name)

    # нормализация легенды в 00_head.md
    if fix_legend_counts():
        if u"00_head.md" not in touched:
            touched.append(u"00_head.md")

    for name in touched:
        if not DRY:
            write(name, norm(read(name)))

    if DRY:
        out = sys.stdout
        try:
            out.reconfigure(encoding="utf-8")
        except Exception:
            pass
        for name in sorted(buckets):
            for title, text in buckets[name]:
                out.write("%-22s | %-50s | %d\n" % (name, title[:50], len(text)))
        out.write("files to touch: %d\n" % len(touched))
        return

    # Если вырезать нечего, тех-файл не трогаем: предыдущий прогон уже всё
    # сложил, и повторный запуск build.py не должен стирать накопленное.
    if not buckets:
        sys.stderr.write("nothing new to extract; tech file left untouched\n")
        return

    emit(buckets)
    sys.stderr.write("extracted %d blocks from %d files -> %s\n"
                     % (sum(len(v) for v in buckets.values()),
                        len(touched),
                        os.path.basename(OUT)))


if __name__ == "__main__":
    main()
