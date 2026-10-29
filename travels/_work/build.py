from __future__ import annotations

from pathlib import Path

BASE = Path(__file__).resolve().parent
W = BASE / "build"
S = BASE / "sections"
OUT = BASE.parent / "Таджикистан.md"

PLACE_ORDER = [
    ("places__Душанбе.md", "Душанбе"),
    ("places__Гиссар_и_Турсунзаде.md", "Гиссар, Турсунзаде и Ширкентское ущелье"),
    ("places__Дорога_Душанбе-Худжанд_Айни_Анзоб.md", "Дорога Душанбе — Худжанд: Айни, Шахристанский и Анзобский перевалы"),
    ("places__Худжанд.md", "Худжанд"),
    ("places__Согд_Истаравшан_Ура-Тюбе_Кайраккум_Исфара_Канибадам.md", "Согд: Истаравшан, Ура-Тюбе, Кайраккум, Исфара, Канибадам"),
    ("places__Пенджикент_и_Зарафшан.md", "Пенджикент и Зеравшанская долина"),
    ("places__Ягноб_и_Фанские_горы.md", "Ягнобская долина и Фанские горы"),
    ("places__Искандеркуль.md", "Озеро Искандеркуль и Могистау"),
    ("places__нурек.md", "Нурек и Нурекская ГЭС"),
    ("places__Хатлон_Бохтар_Курган-Тюбе_Куляб_Шаартуз_Вахда.md", "Хатлон: Бохтар (Курган-Тюбе), Куляб, Шаартуз, Вахш"),
    ("places__Бадахшан_Хорог_Рощан_Шугнан_Ишкошим_Вахан_Зоркуль_Мургаб_Памирский_тракт.md", "Горный Бадахшан: Хорог, Шугнан, Рушан, Ишкашим, Вахан, Зоркуль, Мургаб и Памирский тракт"),
    ("places__Прочее.md", "Страна в целом: города, области, большие объекты"),
]


def strip_top_heading(text: str) -> str:
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].startswith("**") and lines[0].endswith("**"):
        lines.pop(0)
    return "\n".join(lines).strip()


def main() -> None:
    parts = [(W / "00_head.md").read_text(encoding="utf-8").strip()]

    for name in ["10_viza.md", "20_zhile.md", "30_dengi.md", "40_transport.md", "45_svyaz.md"]:
        parts.append((W / name).read_text(encoding="utf-8").strip())

    places = [(W / "50_places_intro.md").read_text(encoding="utf-8").strip()]
    for fname, title in PLACE_ORDER:
        body = strip_top_heading((S / fname).read_text(encoding="utf-8"))
        places.append(f"### {title}\n\n{body}")
    parts.append("\n\n".join(places))

    for name in ["60_eda.md", "70_pokupki.md", "80_prochee.md", "85_fitness.md", "90_med.md",
                 "92_seks.md", "95_zametki.md"]:
        parts.append((W / name).read_text(encoding="utf-8").strip())

    links = (S / "links.md").read_text(encoding="utf-8").strip()
    parts.append((W / "99_links_intro.md").read_text(encoding="utf-8").strip() + "\n\n" + links)

    OUT.write_text("\n\n---\n\n".join(parts) + "\n", encoding="utf-8")
    txt = OUT.read_text(encoding="utf-8")
    print(f"{OUT.name}: {len(txt)} ch, {len(txt.splitlines())} lines, {txt.count(chr(10))+1}")
    for h in [l for l in txt.splitlines() if l.startswith("## ")]:
        # консоль Windows в cp866 Cyrillic и em-dash не печатает
        print("  ", h.encode("ascii", "backslashreplace").decode("ascii"))


if __name__ == "__main__":
    main()
