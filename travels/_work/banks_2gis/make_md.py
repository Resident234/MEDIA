# -*- coding: utf-8 -*-
"""Из banks_2gis/{rows,card}.jsonl → banks_block.md (Душанбе).

usage: python make_md.py

Фильтр: rubric «Банки» (is_bank==True). Для каждого отделения рисуем:
  - **<name>** · lat, lon · [2ГИС](url) · [WhatsApp](wa.me/?text=...) · [Telegram](t.me/...) · _(address)_

WhatsApp: переписываем query `?text=` на стандартный вступительный текст:
  "Здравствуйте. Открываете ли вы карты нерезидентам и на каких условиях ?"
Telegram: ссылка как есть (t.me/+<phone> — предзаполнить сообщение нельзя).
"""
import io
import json
import os
import re
import urllib.parse
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = os.path.join(HERE, "rows.jsonl")
CARDS = os.path.join(HERE, "card.jsonl")
OUT = os.path.join(HERE, "banks_block.md")
HOTLINES = os.path.join(os.path.dirname(HERE), "banks_websites",
                        "hotlines_curated.jsonl")

WA_MESSAGE = (u"Здравствуйте. Открываете ли вы карты нерезидентам "
              u"и на каких условиях ?")
WA_ENCODED = urllib.parse.quote(WA_MESSAGE.encode("utf-8"))

# Банковские сети — группировка внутри района.
NETWORK_PATTERNS = [
    (u"Амонатбонк", re.compile(r"Амонатбонк|Амонатбанк|Amonat", re.UNICODE | re.IGNORECASE)),
    (u"Алиф Банк", re.compile(r"Алиф|Alifa", re.UNICODE | re.IGNORECASE)),
    (u"Атлхам Банк", re.compile(r"Атлхам|Atlas", re.UNICODE | re.IGNORECASE)),
    (u"Бонуди Хайр", re.compile(r"Бонуди\s*Хайр|Boniudi", re.UNICODE | re.IGNORECASE)),
    (u"Давр-Банк", re.compile(r"Давр", re.UNICODE | re.IGNORECASE)),
    (u"Давонон", re.compile(r"Давонон", re.UNICODE | re.IGNORECASE)),
    (u"Ишкол Банк", re.compile(r"Ишкол|Eskhata|Эсхат", re.UNICODE | re.IGNORECASE)),
    (u"Киштхалозбонк", re.compile(r"Киштхалоз", re.UNICODE | re.IGNORECASE)),
    (u"Коммерцбанк (КБТ)", re.compile(r"Коммерцбанк|КБТ|Commercial", re.UNICODE | re.IGNORECASE)),
    (u"Мехргонбанк", re.compile(r"Мехргон|Mehrgan", re.UNICODE | re.IGNORECASE)),
    (u"Мобил-Банк (Тоҷиксодиротбонк)", re.compile(r"Содиротбонк|Содирот", re.UNICODE | re.IGNORECASE)),
    (u"Национальный банк (NBT)", re.compile(r"\bNBT\b|Национал", re.UNICODE | re.IGNORECASE)),
    (u"Омдд Банк", re.compile(r"Омдд|Omdad", re.UNICODE | re.IGNORECASE)),
    (u"Пайванд Банк", re.compile(r"Пайванд|Paywand", re.UNICODE | re.IGNORECASE)),
    (u"Парасбанк", re.compile(r"Парас", re.UNICODE | re.IGNORECASE)),
    (u"Спитамен Банк", re.compile(r"Спитамен|Спаталин|Spitamen|Spitalin", re.UNICODE | re.IGNORECASE)),
    (u"Точикпромбонк (TPB)", re.compile(r"Промбонк|Точикпром|Tajikprom", re.UNICODE | re.IGNORECASE)),
    (u"ТДК Банк", re.compile(r"ТДК|TDC", re.UNICODE | re.IGNORECASE)),
    (u"Фондбанк", re.compile(r"Фондбанк|Fondbank", re.UNICODE | re.IGNORECASE)),
    (u"Эсхата Банк", re.compile(r"Эсхат", re.UNICODE | re.IGNORECASE)),
    (u"И QT / Элтерсан", re.compile(r"IQT|Элтерсан|Eltersan", re.UNICODE | re.IGNORECASE)),
    (u"Афросиаб Банк", re.compile(r"Афросиаб|Afrosiab", re.UNICODE | re.IGNORECASE)),
    (u"Арванд Банк", re.compile(r"Арванд|Arvand", re.UNICODE | re.IGNORECASE)),
    (u"Ансолт Банк", re.compile(r"Ансолт", re.UNICODE | re.IGNORECASE)),
    (u"Душанбе-сити-банк", re.compile(r"Душанбе-сити|Dushanbe-City", re.UNICODE | re.IGNORECASE)),
    (u"Мато (Matin)", re.compile(r"Матin|Матин|Мато", re.UNICODE | re.IGNORECASE)),
]


def network_of(row):
    hay = " ".join([row.get("name") or "", row.get("org_name") or ""])
    for label, rx in NETWORK_PATTERNS:
        if rx.search(hay):
            return label
    return u"Прочие банки"


def district_bucket(d):
    if not d:
        return u"Вне районов"
    m = re.match(r"^(.+?)\s+район$", d)
    if m:
        return u"Район " + m.group(1)
    return d


def rewrite_wa(url):
    """Подменить text= на наш вступительный текст.

    Форма 2ГИС: https://wa.me/<phone>?text=<...>. Если query text
    отсутствует — добавляем. Если есть — заменяем.
    """
    if not url:
        return None
    if "?" in url:
        base = url.split("?", 1)[0]
    else:
        base = url
    return base + "?text=" + WA_ENCODED


def fmt_row(r, card):
    nm = (r.get("name") or "").strip()
    addr = (r.get("address_name") or "").strip()
    lat = r.get("lat")
    lon = r.get("lon")
    url = r.get("url_2gis") or ""
    if lat is None or lon is None:
        return None
    parts = [u"- **%s**" % nm, u"· %.6f, %.6f" % (lat, lon)]
    if url:
        parts.append(u"· [2ГИС](%s)" % url)
    if card:
        wa = card.get("whatsapp_url")
        tg = card.get("telegram_url")
        if wa:
            parts.append(u"· [WhatsApp](%s)" % rewrite_wa(wa))
        if tg:
            parts.append(u"· [Telegram](%s)" % tg)
    if addr:
        parts.append(u"· _(%s)_" % addr)
    return u" ".join(parts)


def load_cards():
    out = {}
    if not os.path.exists(CARDS):
        return out
    for l in io.open(CARDS, encoding="utf-8"):
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if r.get("ok"):
            out[str(r.get("id"))] = r
    return out


def load_hotlines():
    out = []
    if not os.path.exists(HOTLINES):
        return out
    for l in io.open(HOTLINES, encoding="utf-8"):
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    # verified first, then by name
    out.sort(key=lambda r: (not r.get("verified_whatsapp"), r.get("name", "")))
    return out


def render_hotlines():
    rows = load_hotlines()
    if not rows:
        return []
    lines = []
    n_v = sum(1 for r in rows if r.get("verified_whatsapp"))
    lines.append(u"#### Горячие линии — сводка по сетям")
    lines.append(u"")
    lines.append(
        u"_Ниже — официальные номера WhatsApp/Telegram/телефонов каждой "
        u"банковской сети (головной офис отвечает и по отделениям Худжанда). "
        u"Из %d сетей %d публикуют WhatsApp явно (отметка ✅), остальные %d — "
        u"только телефон (в WA-ссылке подставлен основной номер, статус "
        u"«проверьте» — ⚠️). Все WhatsApp-ссылки содержат готовый текст: "
        u"«%s»._"
        % (len(rows), n_v, len(rows) - n_v, WA_MESSAGE))
    lines.append(u"")
    lines.append(u"| Банк | WhatsApp | Telegram | Телефон | Источник | Статус |")
    lines.append(u"|---|---|---|---|---|---|")
    for r in rows:
        nm = r.get("name") or r.get("key") or u"—"
        wa = r.get("wa_url")
        tg = r.get("telegram_url")
        tel = r.get("hotline_text") or u"—"
        site = r.get("site")
        if wa:
            wa_md = u"[wa.me](%s)" % wa
        else:
            wa_md = u"—"
        if tg:
            tg_md = u"[tg](%s)" % tg
        else:
            tg_md = u"—"
        if site:
            src = u"[сайт](%s)" % site
        else:
            src = u"—"
        st = u"✅" if r.get("verified_whatsapp") else (
            u"⚠️" if wa else u"нет WA")
        lines.append(u"| %s | %s | %s | %s | %s | %s |" % (
            nm, wa_md, tg_md, tel, src, st))
    lines.append(u"")
    return lines


def main():
    rows = [json.loads(l) for l in io.open(ROWS, encoding="utf-8") if l.strip()]
    banks = [r for r in rows if r.get("is_bank")]
    cards = load_cards()
    by_dist = defaultdict(lambda: defaultdict(list))
    for r in banks:
        by_dist[district_bucket(r.get("district"))][network_of(r)].append(r)
    dist_order = sorted(
        by_dist.keys(),
        key=lambda d: (-sum(len(v) for v in by_dist[d].values()), d))

    lines = []
    lines.append(u"### Банки — Душанбе")
    lines.append(u"")
    lines.extend(render_hotlines())
    wa_only = sum(1 for r in banks if cards.get(str(r["id"]), {}).get("whatsapp_url"))
    tg_only = sum(1 for r in banks if cards.get(str(r["id"]), {}).get("telegram_url"))
    lines.append(
        u"_Источник: 2ГИС, рубрика «Банки». Снято %d отделений; у %d указан "
        u"WhatsApp, у %d — Telegram. Все WhatsApp-ссылки содержат готовый текст: "
        u"«%s». 2ГИС в Таджикистане индексирует только Душанбе, банки Худжанда "
        u"— ниже отдельным блоком по данным OpenStreetMap (там WhatsApp/Telegram "
        u"не проставлены, только координаты и название)._"
        % (len(banks), wa_only, tg_only, WA_MESSAGE))
    lines.append(u"")

    total_written = 0
    for d in dist_order:
        bucket = by_dist[d]
        d_total = sum(len(v) for v in bucket.values())
        lines.append(u"**%s** — %d отделений" % (d, d_total))
        lines.append(u"")
        # Порядок сетей: по убыванию числа отделений.
        ordered_nets = sorted(
            bucket.keys(),
            key=lambda n: (-len(bucket[n]), n))
        for net in ordered_nets:
            items = sorted(bucket[net], key=lambda r: (r.get("name") or "").lower())
            lines.append(u"_**%s** (%d)_" % (net, len(items)))
            for r in items:
                s = fmt_row(r, cards.get(str(r["id"])))
                if s:
                    lines.append(s)
                    total_written += 1
            lines.append(u"")
        lines.append(u"")

    header = u"<!-- BANKS_DUS_BLOCK_BEGIN -->\n"
    footer = u"\n<!-- BANKS_DUS_BLOCK_END -->\n"
    body = header + u"\n".join(lines).rstrip() + u"\n" + footer
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(body)
    print("wrote %s: %d districts, %d items, %d bytes (wa=%d, tg=%d)"
          % (os.path.basename(OUT), len(dist_order), total_written,
             len(body), wa_only, tg_only))


if __name__ == "__main__":
    main()
