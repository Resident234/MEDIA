from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

BASE = Path(__file__).resolve().parent
W = BASE / "build"
S = BASE / "sections"
OUT = BASE.parent / "Таджикистан.md"
INDEX_NAME = OUT.name

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

SPLIT_EDA = "#### Карточки заведений по городам (Яндекс.Карты)"
SPLIT_SHOP_DUSHANBE = "### Данные карт: категории по Душанбе (2ГИС)"
SPLIT_SHOP_COUNTRY = "### Данные карт: категории по городам страны (Яндекс.Карты)"


class Part(NamedTuple):
    filename: str
    nav: str
    title: str
    body: str


def strip_top_heading(text: str) -> str:
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].startswith("**") and lines[0].endswith("**"):
        lines.pop(0)
    return "\n".join(lines).strip()


def split_before(text: str, heading: str) -> tuple[str, str]:
    marker = "\n" + heading
    pos = text.find(marker)
    if pos < 0:
        if text.startswith(heading):
            return "", text
        raise SystemExit("build: heading not found: " + heading)
    return text[:pos].rstrip(), text[pos + 1:].lstrip("\n")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def h1(part: Part) -> str:
    if part.nav[:1].isdigit():
        return "# Таджикистан — часть " + part.nav
    return "# Таджикистан — " + part.nav


def prev_next(parts: list[Part], idx: int) -> str:
    cells = []
    if idx > 0:
        p = parts[idx - 1]
        cells.append("[← " + p.nav + "](" + p.filename + ")")
    cells.append("[Оглавление](" + INDEX_NAME + ")")
    if idx + 1 < len(parts):
        p = parts[idx + 1]
        cells.append("[" + p.nav + " →](" + p.filename + ")")
    return " · ".join(cells)


def nav_line(parts: list[Part], idx: int) -> str:
    cells = []
    for i, p in enumerate(parts):
        if i == idx:
            cells.append("**" + p.nav + "**")
        else:
            cells.append("[" + p.nav + "](" + p.filename + ")")
    return "**Части:** " + " · ".join(cells)


def index_text(head: str, parts: list[Part]) -> str:
    head = head.strip()
    lines = head.splitlines()
    rest = "\n".join(lines[1:]).strip()
    if rest.endswith("---"):
        rest = rest[:-3].rstrip()
    rows = [
        "## Части файла",
        "",
        "Файл разбит на части: GitHub не рендерит Markdown крупнее 512 КБ. "
        "В начале каждой части — ссылки на все остальные.",
        "",
        "| Часть | Что внутри |",
        "|---|---|",
    ]
    for p in parts:
        rows.append("| [" + p.nav + "](" + p.filename + ") | " + p.title + " |")
    return lines[0] + "\n\n" + "\n".join(rows) + "\n\n" + rest + "\n"


def build_parts() -> list[Part]:
    places = [read(W / "50_places_intro.md")]
    for fname, title in PLACE_ORDER:
        body = strip_top_heading((S / fname).read_text(encoding="utf-8"))
        places.append("### " + title + "\n\n" + body)

    eda_a, eda_b = split_before(read(W / "60_eda.md"), SPLIT_EDA)
    eda_b = "## 7. Еда, чайханы, кафе и алкоголь — продолжение\n\n" + eda_b

    pok = read(W / "70_pokupki.md")
    pok_a, pok_rest = split_before(pok, SPLIT_SHOP_DUSHANBE)
    pok_b, pok_c = split_before(pok_rest, SPLIT_SHOP_COUNTRY)
    pok_b = "## 8. Покупки: базары, магазины, ТЦ и ремёсла — продолжение: карты Душанбе\n\n" + pok_b
    pok_c = "## 8. Покупки: базары, магазины, ТЦ и ремёсла — продолжение: карты по стране\n\n" + pok_c

    links = read(W / "99_links_intro.md") + "\n\n" + read(S / "links.md")

    return [
        Part("Таджикистан_01_виза.md", "1. Виза и регистрация",
             "Сроки пребывания, виза, регистрация, пермиты", read(W / "10_viza.md")),
        Part("Таджикистан_02_жильё.md", "2. Жильё",
             "Жильё: аренда, бронирование, ночёвки в пути", read(W / "20_zhile.md")),
        Part("Таджикистан_03_деньги.md", "3. Деньги и банки",
             "Банки, карты, наличные и переводы из РФ", read(W / "30_dengi.md")),
        Part("Таджикистан_04_транспорт.md", "4. Транспорт",
             "Транспорт", read(W / "40_transport.md")),
        Part("Таджикистан_05_связь.md", "5. Связь и интернет",
             "Связь и интернет", read(W / "45_svyaz.md")),
        Part("Таджикистан_06_места.md", "6. Места",
             "Места, архитектура, достопримечательности", "\n\n".join(places)),
        Part("Таджикистан_07a_еда.md", "7a. Еда",
             "Еда, чайханы, кафе и алкоголь — текст и заведения Душанбе", eda_a),
        Part("Таджикистан_07b_заведения.md", "7b. Заведения по городам",
             "Еда и заведения — карточки по городам, алкоголь, гигиена", eda_b),
        Part("Таджикистан_08a_покупки.md", "8a. Покупки",
             "Покупки: базары, магазины, ТЦ и ремёсла", pok_a),
        Part("Таджикистан_08b_карты_душанбе.md", "8b. Карты: Душанбе",
             "Покупки: данные карт — Душанбе (2ГИС, категории)", pok_b),
        Part("Таджикистан_08c_карты_страна.md", "8c. Карты: страна",
             "Покупки: данные карт — города страны (Яндекс.Карты)", pok_c),
        Part("Таджикистан_09_прочее.md", "9. Прочее",
             "Прочее: язык, этикет, быт, безопасность, сезон", read(W / "80_prochee.md")),
        Part("Таджикистан_10_залы.md", "10. Залы",
             "Тренажёрные залы", read(W / "85_fitness.md")),
        Part("Таджикистан_11_медицина.md", "11. Медицина",
             "Медицина, страховка и здоровье в дороге", read(W / "90_med.md")),
        Part("Таджикистан_12_секс_шопы.md", "12. Секс-шопы",
             "Секс-шопы и секс-товары", read(W / "92_seks.md")),
        Part("Таджикистан_13_знакомства.md", "13. Знакомства",
             "Знакомства: приложения, места, нормы и риски", read(W / "93_dating.md")),
        Part("Таджикистан_14_заметки.md", "14. Заметки",
             "Ваши заметки из таблицы — и ответы на них", read(W / "95_zametki.md")),
        Part("Таджикистан_15_ссылки.md", "Обработанные ссылки",
             "Полный список обработанных ссылок", links),
    ]


def main() -> None:
    parts = build_parts()
    for i, p in enumerate(parts):
        text = (h1(p) + "\n\n" + prev_next(parts, i) + "\n\n" + nav_line(parts, i)
                + "\n\n" + p.body.strip() + "\n")
        (OUT.parent / p.filename).write_text(text, encoding="utf-8")

    head = read(W / "00_head.md")
    index = index_text(head, parts)
    OUT.write_text(index, encoding="utf-8")

    total = len(index.encode("utf-8"))
    print("%s: %d ch, %d lines" % (OUT.name, len(index), len(index.splitlines())))
    for p in parts:
        f = OUT.parent / p.filename
        size = f.stat().st_size
        total += size
        print("  %7d %s" % (size, p.filename.encode("ascii", "backslashreplace").decode("ascii")))
    print("total %d bytes" % total)


if __name__ == "__main__":
    main()
