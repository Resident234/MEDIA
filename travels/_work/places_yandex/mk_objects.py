# -*- coding: utf-8 -*-
"""Извлечь из sections/places__*.md список объектов для привязки к картам.

usage: python mk_objects.py

Каждая секция `places__<slug>.md` в разделе 6 отвечает за конкретный
географический контекст; мы сопоставляем файл с каталогом Яндекса и с
флагом "по Душанбе ли это" (тогда дополнительно ищем в 2ГИС).

Объект = верхнеуровневый bullet (`- ...` без отступа). Имя — текст до
первого `:` или ` (` или `[→`; если ни того, ни другого нет, до первой `.`.
Вложенные bullets (4 пробела + `-`) пропускаем — это уточнения.

Выход: `_objects.tsv` с полями (tab): file / group / raw_name / cleaned /
city_slug / is_dushanbe.
"""
import io
import os
import re
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
S = os.path.join(HERE, "..", "sections")
OUT = os.path.join(HERE, "_objects.tsv")

# Файл -> (Яндекс-каталог, город-контекст, является ли чисто душанбинским).
FILE_MAP = [
    ("places__Душанбе.md",
     ("10318/dushanbe", u"Душанбе", True)),
    ("places__Гиссар_и_Турсунзаде.md",
     ("105973/hisor-district", u"Гиссар/Турсунзаде", False)),
    ("places__Дорога_Душанбе-Худжанд_Айни_Анзоб.md",
     ("105978/rudaki-district", u"Трасса Душанбе-Худжанд (Рудаки/Айни/Анзоб)",
      False)),
    ("places__Худжанд.md",
     ("10322/khujand", u"Худжанд", False)),
    ("places__Согд_Истаравшан_Ура-Тюбе_Кайраккум_Исфара_Канибадам.md",
     ("105968/sughd-province", u"Согд (Истаравшан/Ура-Тюбе/Кайраккум/"
                               u"Исфара/Канибадам)", False)),
    ("places__Пенджикент_и_Зарафшан.md",
     ("10320/pendjikent", u"Пенджикент и Зеравшан", False)),
    ("places__Ягноб_и_Фанские_горы.md",
     ("105968/sughd-province", u"Ягноб/Фанские горы", False)),
    ("places__Искандеркуль.md",
     ("105978/rudaki-district", u"Искандеркуль/Могистау", False)),
    ("places__нурек.md",
     ("10321/nurek", u"Нурек", False)),
    ("places__Хатлон_Бохтар_Курган-Тюбе_Куляб_Шаартуз_Вахда.md",
     ("105969/khatlon-province", u"Хатлон (Бохтар/Куляб/Шаартуз/Вахш)",
      False)),
    ("places__Бадахшан_Хорог_Рощан_Шугнан_Ишкошим_Вахан_Зоркуль_Мургаб_"
     "Памирский_тракт.md",
     ("37175/horog", u"Горный Бадахшан (Хорог/Вахан/Мургаб/Памирский тракт)",
      False)),
    ("places__Прочее.md",
     ("105968/sughd-province", u"Страна в целом", False)),
]

BULLET = re.compile(u"^\\s{0}(?:-|\\*)\\s+(.+)$", re.UNICODE)
GROUP = re.compile(u"^\\*\\*([^*]+)\\*\\*\\s*$", re.UNICODE)
REF = re.compile(u"\\s*\\[\\u2192?\\d[^\\]]*\\]\\([^)]+\\)")
NAME_SPLIT = re.compile(u"[\\u003A\\u003B\\(\\.\\[\\u2192\u2013\u2014]")


def clean_name(raw):
    """Оставляет из bullet-строки только имя объекта."""
    s = REF.sub("", raw)          # убрать [->N](url)
    s = s.replace(u"*", "").strip()
    # Режем по первому разделителю.
    best = len(s)
    for m in NAME_SPLIT.finditer(s):
        best = min(best, m.start())
        break
    # спец-символы: кавычки-«», <>, —
    name = s[:best].strip()
    name = name.replace(u"«", u"").replace(u"»", u"")
    name = name.replace(u"<", u"").replace(u">", u"")
    name = re.sub(u"\u2013|\u2014", u"-", name)
    return name.strip(u" ,.;:")


def parse_file(path):
    group = u""
    out = []
    for line in io.open(path, encoding="utf-8"):
        line = line.rstrip("\n").rstrip("\r")
        g = GROUP.match(line.strip())
        if g:
            group = g.group(1).strip()
            continue
        if not line.startswith(u"- "):
            continue
        raw = line[2:]
        nm = clean_name(raw)
        if not nm or len(nm) < 2:
            continue
        out.append((group, raw, nm))
    return out


def main():
    total = 0
    lines = [u"# file\tgroup\traw\tname\tcity_slug\tcity_ru\tis_dushanbe"]
    for fname, (slug, city_ru, is_dus) in FILE_MAP:
        path = os.path.join(S, fname)
        if not os.path.exists(path):
            print("MISS:", fname)
            continue
        items = parse_file(path)
        for group, raw, nm in items:
            r = raw.replace("\t", " ")
            lines.append(u"%s\t%s\t%s\t%s\t%s\t%s\t%s" % (
                fname, group, r, nm, slug, city_ru,
                "1" if is_dus else "0"))
            total += 1
        print("%-70s %d objects (catalog %s)" % (fname[:70], len(items), slug))
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(
        "\n".join(lines) + "\n")
    print("TOTAL:", total, "->", os.path.basename(OUT))


if __name__ == "__main__":
    main()
