#!/usr/bin/env python3
"""Сбор гостиниц Оша из серверной выдачи 2GIS.

2GIS отдаёт первые пять страниц поиска в SSR JSON. Рейтинг и контакты
дублируются в SSR JSON карточки организации, поэтому API-ключ не нужен.
"""
from __future__ import annotations

import json
import re
import time
from html import unescape
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

BASE = "https://2gis.kg"
SEARCH_URL = BASE + "/osh/search/%D0%93%D0%BE%D1%81%D1%82%D0%B8%D0%BD%D0%B8%D1%86%D1%8B/rubricId/269/filters/rating_rating_pretty_good/page/{}?m=72.779492%2C40.513767%2F12.19"
OUT = Path(__file__).with_name("osh_hotels_whatsapp.md")
SPA_PAGES = Path(__file__).with_name("browser_pages.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MEDIA research parser/1.0)"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def initial_state(html: str) -> dict[str, Any]:
    """Извлекает JSON из var initialState = JSON.parse('...')."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script"):
        text = script.string or script.get_text()
        marker = "var initialState = JSON.parse('"
        start = text.find(marker)
        if start < 0:
            continue
        start += len(marker)
        # Ищем закрывающую кавычку, не экранированную обратным слешем.
        match = re.search(r"(?<!\\)'\);", text[start:], flags=re.S)
        if not match:
            continue
        encoded = text[start : start + match.start()]
        # Строка JSON в SSR использует стандартные JS-экранирования.
        decoded = encoded.encode("utf-8").decode("unicode_escape")
        # unicode_escape корректно разворачивает \u/\n, но ошибочно
        # трактует уже UTF-8-кодированные кириллические байты как Latin-1.
        if "Ð" in decoded or "Ñ" in decoded:
            decoded = decoded.encode("latin-1").decode("utf-8")
        return json.loads(decoded)
    raise RuntimeError("initialState не найден в HTML 2GIS")


def profiles_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = state["data"]["entity"]["profile"]
    result = []
    for branch_id, wrapper in profiles.items():
        data = wrapper.get("data", wrapper)
        data = dict(data)
        data.setdefault("id", branch_id)
        result.append(data)
    return result


def get(url: str) -> str:
    response = SESSION.get(url, timeout=45)
    response.raise_for_status()
    return response.text


def card_url(branch_id: str, data: dict[str, Any] | None = None) -> str:
    alias = "osh"
    if data:
        for adm in data.get("adm_div", []):
            if adm.get("type") == "city" and adm.get("city_alias"):
                alias = adm["city_alias"]
                break
    return f"{BASE}/{alias}/firm/{branch_id}"


def whatsapp(data: dict[str, Any]) -> str | None:
    for group in data.get("contact_groups", []):
        for contact in group.get("contacts", []):
            if contact.get("type") == "whatsapp":
                return contact.get("value") or contact.get("url")
    return None


def md_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def main() -> None:
    all_items: dict[str, dict[str, Any]] = {}
    if SPA_PAGES.exists():
        # Страницы 2GIS с фильтром подгружаются SPA; прямой HTTP-запрос
        # после пятой страницы сбрасывается на первую, поэтому список,
        # снятый из DOM браузера, сохраняется как промежуточный источник.
        pages = json.loads(SPA_PAGES.read_text(encoding="utf-8"))
        for page, rows in pages.items():
            for row in rows:
                if "/osh/firm/" in row.get("url", ""):
                    all_items[str(row["id"])] = row
            print(f"Страница {page}: уникальных карточек Оша {len(all_items)}")
    else:
        raise RuntimeError(
            f"Не найден {SPA_PAGES}. Сначала сохраните полный список SPA-страниц 2GIS."
        )

    rated = []
    for item in all_items.values():
        # В DOM SPA рейтинг отображается текстом, а не в ссылке; все
        # карточки здесь уже отобраны интерфейсным фильтром «от 4».
        rating = item.get("reviews", {}).get("general_rating") or item.get("rating") or 4.0
        if float(rating) >= 4.0:
            item["rating"] = float(rating)
            rated.append(item)
    print(f"Найдено карточек: {len(all_items)}, рейтинг 4.0+: {len(rated)}")

    detailed: list[dict[str, Any]] = []
    for index, item in enumerate(rated, 1):
        branch_id = str(item["id"])
        try:
            data = profiles_from_state(initial_state(get(card_url(branch_id, item))))[0]
            actual_rating = data.get("reviews", {}).get("general_rating", item["rating"])
            item = {**item, **data, "id": branch_id, "rating": float(actual_rating)}
        except Exception as exc:  # карточка может временно не отдаться
            print(f"Предупреждение: карточка {branch_id}: {exc}")
        if float(item["rating"]) >= 4.0:
            detailed.append(item)
        print(f"Карточка {index}/{len(rated)}: {item.get('name', branch_id)}")
        time.sleep(0.25)

    detailed.sort(key=lambda x: (-float(x["rating"]), str(x.get("name", "")).lower()))
    with OUT.open("w", encoding="utf-8", newline="\n") as out:
        out.write("# Гостиницы Оша из 2ГИС (рейтинг 4.0+)\n\n")
        out.write(
            "Собрано из полной SPA-выдачи 2GIS по рубрике «Гостиницы» с фильтром "
            "рейтинга «от 4»; оставлены только карточки с URL города Ош. "
            f"Всего организаций с рейтингом 4.0+: {len(detailed)}.\n\n"
        )
        for item in detailed:
            name = md_value(item.get("name") or "Без названия")
            rating = item["rating"]
            rating_text = str(int(rating)) if rating.is_integer() else f"{rating:.1f}"
            address = md_value(item.get("address_name") or "адрес не указан")
            branch_id = str(item["id"])
            wa = whatsapp(item)
            out.write(f"## {name}\n\n")
            out.write(f"**Рейтинг:** {rating_text}\n\n")
            out.write(f"**Адрес:** {address}\n\n")
            url = card_url(branch_id, item)
            out.write(f"**Карточка 2ГИС:** [{url}]({url})\n\n")
            out.write(
                f"**WhatsApp:** [WhatsApp]({wa})\n\n" if wa
                else "**WhatsApp:** _WhatsApp не указан_\n\n"
            )
    print(f"Готово: {OUT} ({len(detailed)} записей)")


if __name__ == "__main__":
    main()
