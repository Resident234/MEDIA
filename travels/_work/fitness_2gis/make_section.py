# -*- coding: utf-8 -*-
"""Генерирует блоки строк для раздела 10 из собранных через 2GIS API данных.

Ничего не выдумывает: берёт поля карточек дословно, родовые слова и рубрики
переводит по справочнику, который тоже пришёл из выдачи API (фасет rubrics
с русскими названиями). Вывод — UTF-8 файл section_parts.txt, его текст
вставляется в build/85_fitness.md.
"""
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
ge4 = json.load((BASE / "ge4_final.json").open(encoding="utf-8"))
allx = json.load((BASE / "items_ru.json").open(encoding="utf-8"))
branches = json.load((BASE / "branches.json").open(encoding="utf-8"))

RUBRIC_RU = {
    "267": "тренажёрные залы", "268": "фитнес-клубы", "51256": "спортивные секции",
    "261": "бассейны", "20228": "центры йоги", "1233": "спортивное питание",
    "4515": "обучение танцам", "56759": "SPA-процедуры", "110354": "занятия ЛФК",
    "946": "бани и сауны", "13726": "массажист", "110498": "аренда спортплощадок",
    "112847": "нутрициолог",
}
MAIN = {"267", "268"}


def floor(comment):
    if not comment:
        return None
    value = comment.replace("ошёнаи:", "").strip()
    if value == "таҳхона":
        return "подвал"
    if re.fullmatch(r"-?\d+", value):
        n = value.lstrip("-")
        return "этаж \u2212" + n if value.startswith("-") else "этаж " + n.replace("-", "\u2013")
    return "этажи " + value.replace("-", "\u2013")


def address(item):
    addr = item.get("address_ru") or item.get("address")
    return addr


def district(item):
    raw = item.get("district_ru") or item.get("district") or ""
    return raw.replace(" район", "").strip()


def extras(item):
    out = []
    for code in item.get("rubric_ids") or []:
        if code in MAIN:
            continue
        name = RUBRIC_RU.get(code)
        if name:
            out.append(name)
    return out


lines = []

# --- блок 1: залы с рейтингом >= 4.0 ---
for i, it in enumerate(ge4, 1):
    parts = ["**%s**" % it["name"]]
    rc = it.get("review_count")
    fld = "general_rating" if it.get("rating_field") == "general_rating" else "org_rating"
    parts.append("рейтинг %.1f, отзывов %d, поле %s" % (it["rating"], rc or 0, fld))
    loc = []
    d = district(it)
    if d:
        loc.append("район %s" % d)
    addr = address(it)
    loc.append(addr if addr else "адрес в выдаче API не отдан, только координаты")
    fl = floor(it.get("address_comment"))
    if fl:
        loc.append(fl)
    parts.append(", ".join(loc))
    parts.append("координаты (широта, долгота) %.6f, %.6f" % (it["lat"], it["lon"]))
    ex = extras(it)
    if ex:
        parts.append("рубрики кроме зала: " + ", ".join(ex))
    parts.append("карточка: %s" % it["url_2gis"])
    lines.append("- " + "; ".join(parts) + ".")

block_halls = "\n".join(lines)

# --- блок 2: несколько карточек под одним именем ---
lines = []
for grp in branches:
    if grp["name"] in ("Толори варзишӣ", "Толори варзишии занона", "Клуби варзишӣ", "Фитнес клуб"):
        continue
    noaddr = sum(1 for r in grp["rows"] if r["addr"] == "—")
    adds = [r["addr"] for r in grp["rows"] if r["addr"] != "—"]
    rated = [r["rating"] for r in grp["rows"] if r["rating"] is not None]
    bits = adds[:]
    if noaddr:
        bits.append("ещё %d без адреса в выдаче" % noaddr)
    lines.append("- **%s** — %d карточки (%s); рейтинг в выдаче: %s." % (
        grp["name"], grp["n"], "; ".join(bits) if bits else "—",
        ", ".join("%.1f" % r for r in rated) if rated else "не отдан ни у одной"))
block_branches = "\n".join(lines)

# --- блок 3: безымянные залы ---
unnamed = [g for g in branches if g["name"] in
           ("Толори варзишӣ", "Толори варзишии занона", "Клуби варзишӣ", "Фитнес клуб")]
block_unnamed = "\n".join(
    "- «%s» — %d карточек (%s)." % (
        g["name"], g["n"],
        ", ".join((r["addr"] if r["addr"] != "—" else "без адреса") for r in g["rows"]))
    for g in unnamed)

# --- сводка ---
no_rating = sum(1 for x in allx if x.get("rating") is None)
below = [x for x in allx if isinstance(x.get("rating"), (int, float)) and x["rating"] < 4.0]
from collections import Counter
dist = Counter(district(x) for x in allx)
report = json.load((BASE / "collect_report.json").open(encoding="utf-8"))
req = report.get("requests_made")
block_stats = "\n".join([
    "- Всего уникальных карточек: %d (четыре рубрики и оба текстовых запроса, %d обращений к API)." % (
        len(allx), req),
    "- Рейтинга нет вообще: %d карточек из %d (%.0f %%)." % (
        no_rating, len(allx), 100.0 * no_rating / len(allx)),
    "- Рейтинг 4.0 и выше: %d; ниже 4.0: %d (%s)." % (
        len(ge4), len(below), ", ".join("%.1f" % b["rating"] for b in below)),
    "- Районы по всем %d карточкам: %s." % (
        len(allx), ", ".join("%s %d" % (k, v) for k, v in dist.most_common())),
])

out = "\n\n=== HALLS ===\n\n%s\n\n=== BRANCHES ===\n\n%s\n\n=== UNNAMED ===\n\n%s\n\n=== STATS ===\n\n%s\n" % (
    block_halls, block_branches, block_unnamed, block_stats)
(BASE / "section_parts.txt").write_text(out, encoding="utf-8")
print("halls=%d branches=%d unnamed_groups=%d stats lines=4" % (len(ge4), len(lines), len(unnamed)))
