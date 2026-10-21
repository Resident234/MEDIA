# -*- coding: utf-8 -*-
"""Куранная таблица «Горячие линии банков Таджикистана».

Source: WebSearch + официальные сайты + 2GIS card.jsonl (данные на 2026-10-21).
verified=True  → банк прямо публикует номер как WhatsApp (wa.me, «WhatsApp» в
                 тексте или на /contacts странице)
verified=False → публичного WA-номера нет; в wa.me подставлен основной телефон
                 hotline — пользователь может попробовать, но это лотерея.

usage: python build_hotlines.py
"""
import io
import json
import os
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "hotlines_curated.jsonl")

WA_MESSAGE = (u"Здравствуйте. Открываете ли вы карты нерезидентам "
              u"и на каких условиях ?")
WA_ENCODED = urllib.parse.quote(WA_MESSAGE.encode("utf-8"))

# bank_key, display_name, wa_phone (digits, leading 992), hotline_text, tg, site, verified, note
DATA = [
    ("Амонатбонк",
     "Амонатбонк (ОАО Сберегательный банк РТ)",
     "992900004826", "+992 900 00 48 26", None,
     "https://amonatbonk.tj/ru/about/information/contacts/", True,
     "Опубликовано в шапке Contacts"),
    ("Алиф",
     "Алиф Банк (OAO Alif Bank)",
     "992900909080", "+992 900 90 90 80", "https://t.me/alifbank",
     "https://alif.tj/", True,
     "Viber / WhatsApp на 900 90 90 80 (call center 48 888 1111)"),
    ("Арванд",
     "Банк Арванд (ЗАО)",
     "992929149333", "+992 92 914 93 33", "https://t.me/+992929149333",
     "https://arvand.tj/about/contacts/", True,
     "Instagram: 'Пишите или звоните в Telegram/WhatsApp'"),
    ("Душанбе-Сити-Банк",
     "Душанбе Сити Банк (ЗАО)",
     None, "+992 44 630 99 99", "https://t.me/dushanbecity_tj",
     "https://dc.tj/", False,
     "web.whatsapp.com: 44 630 99 99 не зарегистрирован (проверено 2026-10-21); "
     "WA на сайте/YMaps не опубликован. Звоните hotline."),
    ("Имон Интернешнл",
     "Imon International Bank (ЗАО МДО)",
     "992928455505", "+992 92 845 55 05", None,
     "https://imon.tj/en", True,
     "Facebook: '+992 92 845 55 05 (whatsapp, telegram, viber)'"),
    ("Ишкола",
     "Ишкола (Сомондиён) банк",
     None, "—", None, None, False,
     "WA/public hotline не найдены; на 2GIS — только адреса"),
    ("КБТ",
     "Коммерцбанк Таджикистана (КБТ)",
     "992777090197", "+992 77 709 01 97", "https://t.me/cbttj",
     "https://cbt.tj/contact", True,
     "FB video 2026: 'WhatsApp +992777090197'; hotline 2200 / +992 44 630 88 88"),
    ("Хумо",
     "Хумо Банк (ЗАО)",
     None, "+992 88 777 55 44", None,
     "https://humo.tj/ru", False,
     "web.whatsapp.com: 88 777 55 44 не зарегистрирован (2026-10-21), хотя "
     "FB/сайт указывали как WA. Звоните hotline."),
    ("ICB",
     "ICB — Первый Микрофинансовый Банк (ЗАО ИКБТ)",
     "992771110111", "+992 77 111 0 111", None,
     "https://icb.tj/EN/ICB-mobile?type=1", True,
     "Официальный текст ICB Mobile: 'via Telegram and WhatsApp +992 77 111 0 111'"),
    ("IBT",
     "IBT — Международный Банк Таджикистана (ЗАО МБТ)",
     None, "+992 44 625 77 77", "https://t.me/ibt_tajikistan",
     "https://www.ibt.tj/contacts/", False,
     "web.whatsapp.com: 44 625 77 77 не зарегистрирован (2026-10-21). "
     "На /contacts только телефон/1155. WA нет."),
    ("Ориёнбанк",
     "Ориёнбанк (ОАО)",
     None, "+992 44 610 22 00", None,
     "https://oriyonbonk.tj/ru/", False,
     "web.whatsapp.com: 44 610 22 00 не зарегистрирован (2026-10-21). "
     "WA нет. Hotline 2222 / +992 44 610 22 00."),
    ("Пайванд",
     "Пайванд Групп (ЗАО МДО)",
     None, "+992 988 88 61 61", None,
     "https://www.payvand.tj/ru/contacts/contact", False,
     "web.whatsapp.com: 988 88 61 61 не зарегистрирован (2026-10-21). "
     "Горячая линия 5505. WA нет."),
    ("Спитамен",
     "Спитамен Банк (ЗАО)",
     None, "+992 888 656 565", None,
     "https://www.spitamenbank.tj/ru/loan-application/", False,
     "web.whatsapp.com: 888 656 565 не зарегистрирован (2026-10-21), хотя "
     "loan-application указывал как WA/Telegram. Звоните hotline."),
    ("Тахвидбанк",
     "Тавхидбанк / Тахвидбанк (ОАО)",
     None, "+992 44 601 70 70", None,
     "https://www.tawhidbank.tj/", False,
     "web.whatsapp.com: 44 601 70 70 не зарегистрирован (2026-10-21). "
     "На сайте/YMaps только телефон/9111. WA нет."),
    ("Эсхата",
     "Банк Эсхата (ОАО)",
     None, "+992 44 600 0 600", None,
     "https://www.eskhata.com/", False,
     "web.whatsapp.com: 44 600 0 600 не зарегистрирован (2026-10-21). "
     "Contact-центр 808. WA нет."),
    ("Мехргон",
     "Мехргонбанк (ЗАО)",
     None, "—", None, None, False,
     "Официальный сайт недоступен (DNS fail), WA не найден"),
    ("Фондбанк",
     "Фондбанк Таджикистана",
     None, "—", None, None, False,
     "Официальный сайт недоступен (DNS fail), WA не найден"),
    ("Киштхалозбонк",
     "Киштхалозбонк (ЗАО)",
     None, "—", None, None, False,
     "Официальный сайт ktb.tj — connect timeout"),
    ("Активбанк",
     "Активбанк (ЗАО)",
     "992988077111", "+992 988 077 111", None,
     "https://activbank.tj/about-bank/kontakty-i-rekvizity", True,
     "Есть в 2GIS card.jsonl: wa.me/992988077111"),
    ("Freedom",
     "Freedom Bank Таджикистан (ЗАО)",
     "992555005599", "+992 555 00 55 99", None,
     None, True,
     "Есть в 2GIS card.jsonl: wa.me/992555005599"),
    ("NBT",
     "Национальный Банк Таджикистана (регулятор)",
     None, "+992 44 600 32 27", "https://t.me/nbt_tj",
     "https://nbt.tj/ru/", False,
     "Регулятор, не обслуживает физлиц; WA не публикуется (сайт, YMaps)"),
    ("Матин",
     "МФСО Матин (Микрофинансовая организация)",
     None, "—", None, None, False,
     "Сайт matin.tj не отвечает, WA не найден"),
]


def wa_link(digits):
    if not digits:
        return None
    return "https://wa.me/%s?text=%s" % (digits, WA_ENCODED)


def main():
    fh = io.open(OUT, "w", encoding="utf-8", newline="\n")
    n_v = 0
    for (key, name, wa_digits, hotline_text, tg, site, verified, note) in DATA:
        rec = {
            "key": key,
            "name": name,
            "wa_phone": wa_digits,
            "wa_url": wa_link(wa_digits),
            "hotline_text": hotline_text,
            "telegram_url": tg,
            "site": site,
            "verified_whatsapp": bool(verified),
            "note": note,
        }
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if verified:
            n_v += 1
    fh.close()
    print("wrote %d records (%d verified WA) to %s" % (
        len(DATA), n_v, OUT))


if __name__ == "__main__":
    main()
