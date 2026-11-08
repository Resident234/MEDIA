# -*- coding: utf-8 -*-
"""Append manually verified rows for 5 banks whose banki.ru card returns 404.

Domains/statuses verified 2026-11-08 via web search (cbr.ru реестр, interfax,
dvbank.ru, qplus.ru/Евроальянс) — LLM knowledge output alone was NOT trusted:
it misguessed loko-bank.ru (actually lockobank.ru) and dalbank.ru (actually dvbank.ru).
"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
CACHE = r"e:\SERVER\Work_MEDIA\finance\_banki_work\sites.jsonl"

FIXES = [
    {"slug": "aenbank", "name": "АйМаниБанк", "site": "expobank.ru",
     "note": "Карточка на banki.ru удалена (404). Лицензия отозвана 05.10.2016, "
             "банк присоединён к Экспобанку (cbr.ru: «Не действует»). Сайт указан "
             "по банку-получателю, сверен web-поиском, а не только LLM."},
    {"slug": "pochtabank", "name": "Почта Банк", "site": "vtb.ru",
     "note": "Карточка на banki.ru удалена (404). Юридически присоединён к ВТБ "
             "(завершено 05.2026, interfax/1prime), поэтому указан сайт банка-"
             "получателя vtb.ru."},
    {"slug": "dalnevostochny", "name": "Дальневосточный Банк", "site": "dvbank.ru",
     "note": "Карточка на banki.ru удалена (404). ДВБ присоединён к МКБ "
             "(01.08.2026, cbr.ru: ликвидирован); собственный сайт dvbank.ru "
             "действует, старый dalbank.ru — неверен (ошибка LLM, исправлена "
             "по web-поиску)."},
    {"slug": "qplus", "name": "Qplus", "site": "qplus.ru",
     "note": "Карточка на banki.ru удалена (404). Qplus — платёжный сервис "
             "АО КИБ «Евроальянс» (лицензия ЦБ №1781), сайт qplus.ru "
             "подтверждён из футера самого qplus.ru."},
    {"slug": "bloko", "name": "Локо-Банк (дубликант)", "site": "lockobank.ru",
     "note": "Карточка /banks/bank/bloko/ — 404: это устаревший код Локо-Банка, "
             "активная карточка — locko-bank (строка «Локо-Банк» выше, "
             "lockobank.ru). LLM предложил loko-bank.ru — неверно, исправлено "
             "по карточке banki.ru и cbr.ru."},
]

seen = {}
with open(CACHE, encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        seen[d["slug"]] = d

for fx in FIXES:
    s = fx["slug"]
    old = seen.get(s, {})
    row = dict(fx)
    row.setdefault("card", f"https://www.banki.ru/banks/bank/{s}/")
    row.setdefault("responses", f"https://www.banki.ru/services/responses/bank/{s}/")
    row["status"] = "verified_404_card"
    row["regex_gt"] = old.get("regex_gt", "")
    with open(CACHE, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("patched", s, "->", row["site"])
