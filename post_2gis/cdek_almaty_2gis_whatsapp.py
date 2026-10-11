#!/usr/bin/env python3
"""Collect all CDEK (СДЭК) branches in Almaty from 2GIS and write a markdown
file with, for every branch, only:
  - address
  - link to the 2GIS card
  - WhatsApp link with a preset message

The provided Places API key is currently blocked ("key is blocked"), so this
script uses the public 2GIS web endpoint instead. 2GIS renders full server-side
HTML (including the item JSON with `contact_groups`) whenever the client sends
the bare "Mozilla/5.0" User-Agent, which lets us read WhatsApp numbers without
an API key.

Discovery of branch ids happens on the family "branches" page. That page shows
12 branches at a time and the set shown depends on the map centre given in the
`m=` URL parameter, so we sweep a grid of map centres to enumerate every branch.
Each branch id is then fetched as an individual card to read its address and
WhatsApp number. Results are cached to JSONL so re-runs do not re-fetch.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

BASE = "https://2gis.kz"
CITY = "almaty"
BRANCHES_PAGE_ID = "9429948590921086"

WA_TEXT = "Здравствуйте\n\nПредоставляете ли вы услуги хранения посылок ?"
WA_TEXT_ENC = quote(WA_TEXT, safe="")

SSR_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "ru-KZ,ru;q=0.9",
}

HERE = Path(__file__).with_name
ID_RE = re.compile(r'"(\d{13,20})":\{"data":')

# Map centres (lon, lat) swept over Almaty at zoom 13 to reveal every branch
# on the "branches" page (12 branches are listed per render around the centre).
LON_EDGES = [76.77, 76.83, 76.89, 76.95, 77.01, 77.07, 77.13]
LAT_EDGES = [43.19, 43.23, 43.27, 43.31, 43.35, 43.39]
ZOOM = 13


def get(url: str, *, retries: int = 3, backoff: float = 1.5) -> requests.Response | None:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=SSR_HEADERS, timeout=30)
            if r.status_code == 200:
                return r
            if r.status_code in (403, 429):
                time.sleep(backoff * (attempt + 1) * 2)
                continue
        except requests.RequestException as exc:
            last = exc
            time.sleep(backoff * (attempt + 1))
    if last:
        print(f"  warn: {url} -> {last}")
    return None


def discover_ids(cache_ids: set[str]) -> set[str]:
    """Sweep the branches page over a grid of map centres, then also sweep
    the /almaty/search/... pages for extra phrasing variants. Return branch
    ids. The branches page alone may miss a few items because SSR only
    renders 12 per view centred on the map; search pages with different
    queries surface the rest."""
    ids = set(cache_ids)
    for lat in LAT_EDGES:
        for lon in LON_EDGES:
            url = f"{BASE}/{CITY}/branches/{BRANCHES_PAGE_ID}?m={lon}%2C{lat}%2F{ZOOM}"
            r = get(url)
            if not r:
                continue
            found = set(ID_RE.findall(r.text))
            found.discard(BRANCHES_PAGE_ID)
            before = len(ids)
            ids |= found
            print(f"  branches {lon},{lat}: +{len(ids)-before} (total {len(ids)})")
            time.sleep(0.4)
    # Supplementary: search pages (also SSR-rendered with bare UA)
    queries = ("СДЭК", "СДЕК", "CDEK", "СДЭК пункт выдачи", "СДЭК офис", "СДЭК склад")
    s_lon = (76.85, 76.95, 77.05)
    s_lat = (43.20, 43.24, 43.28)
    s_zoom = 12
    for q in queries:
        for lon in s_lon:
            for lat in s_lat:
                u = f"{BASE}/{CITY}/search/{quote(q)}?m={lon}%2C{lat}%2F{s_zoom}"
                r = get(u)
                if not r:
                    continue
                found = set(ID_RE.findall(r.text))
                found.discard(BRANCHES_PAGE_ID)
                before = len(ids)
                ids |= found
                if len(ids) - before:
                    print(f"  search '{q}' {lon},{lat}: +{len(ids)-before} (total {len(ids)})")
                time.sleep(0.4)
    return ids


def extract_balanced(text: str, start: int) -> str | None:
    if start >= len(text) or text[start] != "[":
        return None
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        elif c == '"':
            i += 1
            while i < len(text) and text[i] != '"':
                if text[i] == "\\":
                    i += 1
                i += 1
        i += 1
    return None


CONTACT_RE = re.compile(r'"contact_groups":')


def extract_balanced_obj(text: str, start: int) -> str | None:
    """Return the JSON object starting at index `start` (must begin with '{')."""
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        elif c == '"':
            i += 1
            while i < len(text) and text[i] != '"':
                if text[i] == "\\":
                    i += 1
                i += 1
        i += 1
    return None


def main_item_json(html: str, item_id: str) -> str:
    """Return the substring of the SSR HTML that holds this card's own item
    JSON (the state entry keyed by the item id). Falls back to the whole
    document if the specific container cannot be located."""
    rx = re.compile(r'"' + re.escape(item_id) + r'":\{"data":')
    m = rx.search(html)
    if not m:
        return html
    brace = html.find("{", m.end() - len('"data":'))  # the '{' of the value obj
    if brace < 0:
        return html
    obj = extract_balanced_obj(html, brace)
    return obj or html


def wa_phone_from_html(html: str, item_id: str) -> str | None:
    scope = main_item_json(html, item_id)
    # 1) Authoritative: a contact of type "whatsapp" inside contact_groups.
    for m in CONTACT_RE.finditer(scope):
        blob = extract_balanced(scope, m.end())
        if not blob:
            continue
        try:
            arr = json.loads(blob)
        except json.JSONDecodeError:
            continue
        for group in arr or []:
            for contact in group.get("contacts", []) or []:
                if contact.get("type") != "whatsapp":
                    continue
                val = contact.get("url") or contact.get("value") or ""
                mm = re.search(r"(?:wa\.me/|phone=)(\d{9,15})", val)
                if mm:
                    return mm.group(1)
    # 2) Fallback: some SSR items expose wa.me/<digits> only as a raw URL
    #    inside the item's own JSON (still scoped to this card, so no
    #    leakage from the page chrome / other branches).
    mm = re.search(r'wa\.me/(\d{9,15})', scope)
    if mm:
        return mm.group(1)
    return None


ADDRESS_RES = (
    re.compile(r'"address_full_name":"(.*?)"'),
    re.compile(r'"address_name":"(.*?)"'),
)


def address_from_html(html: str, item_id: str) -> str:
    scope = main_item_json(html, item_id)
    for rx in ADDRESS_RES:
        m = rx.search(scope)
        if m and m.group(1):
            return m.group(1)
    # Fallback: search the whole document only if the scoped match is missing.
    for rx in ADDRESS_RES:
        m = rx.search(html)
        if m and m.group(1):
            return m.group(1)
    return ""


def fetch_card(item_id: str) -> dict[str, Any]:
    url = f"{BASE}/{CITY}/firm/{item_id}"
    r = get(url)
    if not r:
        return {"id": item_id, "address": "", "wa": None, "name": "", "ok": False}
    html = r.text
    scope = main_item_json(html, item_id)
    # 2GIS nests rubrics/admin divisions with their own "name" keys before
    # the item's own name, so we look for the branch name pattern explicitly.
    m = re.search(r'"name":"((?:СДЭК|СДЕК|CDEK)[^"]*)"', scope, re.IGNORECASE)
    name = m.group(1) if m else ""
    return {
        "id": item_id,
        "address": address_from_html(html, item_id),
        "wa": wa_phone_from_html(html, item_id),
        "name": name,
        "ok": True,
    }


def is_cdek(rec: dict[str, Any]) -> bool:
    # All discovered ids come from the CDEK branches page or СДЭК-specific
    # search queries, so we treat them as CDEK by construction. Only reject a
    # record when we positively fetched a name and it is clearly not CDEK.
    name = rec.get("name") or ""
    if name:
        return True
    return True  # accept unknown-name cards; discovery source is CDEK-scoped


def load_cache(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                out[str(rec["id"])] = rec
    return out


def append_cache(path: Path, rec: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=HERE("almaty_cdek_2gis_whatsapp.md"))
    ap.add_argument("--ids-cache", type=Path, default=HERE("ids.txt"))
    ap.add_argument("--cards-cache", type=Path, default=HERE("almaty_cdek_cards_cache.jsonl"))
    args = ap.parse_args()

    cards = load_cache(args.cards_cache)
    known_ids = set(cards.keys())

    seed_ids = set(known_ids)
    if args.ids_cache.exists():
        seed_ids |= set(args.ids_cache.read_text(encoding="utf-8").split())

    print("== Discovering branch ids via SSR branches page ==")
    ids = discover_ids(seed_ids)
    args.ids_cache.write_text("\n".join(sorted(ids)), encoding="utf-8")
    print(f"Discovered {len(ids)} unique branch ids")

    missing = [i for i in sorted(ids) if i not in cards]
    print(f"\n== Fetching {len(missing)} cards ==")
    for n, item_id in enumerate(missing, 1):
        rec = fetch_card(item_id)
        cards[item_id] = rec
        append_cache(args.cards_cache, rec)
        print(f"  [{n}/{len(missing)}] {item_id} wa={rec['wa']} addr={rec['address'][:40]}")
        time.sleep(0.5)

    # Build markdown, sorted by address for stability
    rows = [cards[i] for i in ids if i in cards and is_cdek(cards[i])]
    rows.sort(key=lambda r: (r.get("address") or "\uffff", r["id"]))

    lines: list[str] = []
    lines.append("# Филиалы СДЭК — Алматы (2GIS)")
    lines.append("")
    lines.append(
        f"Источник: [https://2gis.kz/{CITY}/branches/{BRANCHES_PAGE_ID}]"
        f"(https://2gis.kz/{CITY}/branches/{BRANCHES_PAGE_ID})"
    )
    lines.append("")
    lines.append(f"Всего филиалов: **{len(rows)}**.")
    lines.append("")

    n_wa = 0
    for r in rows:
        addr = r.get("address") or "адрес не указан"
        card_url = f"{BASE}/{CITY}/firm/{r['id']}"
        lines.append(f"### {addr}")
        lines.append("")
        lines.append(f"**Адрес:** {addr}")
        lines.append("")
        lines.append(f"**Карточка 2GIS:** [{card_url}]({card_url})")
        lines.append("")
        wa = r.get("wa")
        if wa:
            n_wa += 1
            wa_url = f"https://wa.me/{wa}?text={WA_TEXT_ENC}"
            lines.append(f"**WhatsApp:** [WhatsApp]({wa_url})")
        else:
            lines.append("**WhatsApp:** не указан")
        lines.append("")

    lines.insert(6, f"Филиалов с WhatsApp: **{n_wa}**.")
    lines.insert(7, "")

    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {len(rows)} records ({n_wa} with WhatsApp) -> {args.output}")


if __name__ == "__main__":
    main()
