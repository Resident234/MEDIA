# -*- coding: utf-8 -*-
"""Insert contact info into the 19 hall lines of build/85_fitness.md.

Каждой строке зала (определяется по URL карточки firm/<id>) перед
"; карточка:" вставляется блок контактов, снятых с SSR-страниц 15.10.2026.
Также переписываются три пункта в «Что осталось незакрытым».
"""
import io
import re

P = "build/85_fitness.md"
INS = {
    "70000001103044666": "телефон +992 488 88 85 55; Telegram: https://t.me/+992Xfitdushanbe1 (запись в карточке — склейка кода страны и имени, возможно ошибка ввода); сайт http://x-fit.tj, почта info@x-fit.tj; Instagram: https://instagram.com/XFITDUSHANBE; часы: пн–пт 06:00–23:00, сб–вс 07:00–22:00; ",
    "70000001101445485": "телефон +992 446 40 55 55; сайт http://dorobgym.com; Instagram: https://instagram.com/dorobgym.kurushikabir; Facebook: https://facebook.com/DorobGym; часы: пн–вс 06:30–23:00; ",
    "70000001104026887": "телефон +992 882 08 54 45; WhatsApp: https://wa.me/992882085445; Telegram: https://t.me/+992882085445; Instagram: https://instagram.com/energy_gym_91; часы: пн–сб 08:30–22:00; ",
    "70000001101226012": "телефоны 974 69 00 06, +992 000 00 02 38 и 906 78 40 04; WhatsApp: https://wa.me/992974690006 и https://wa.me/992000000238; Instagram: https://instagram.com/evolution_team_bayonov; часы: пн–сб 09:00–21:00; ",
    "70000001100799532": "телефон 904 11 80 08; Instagram: https://instagram.com/leader_gym_official; часы: пн–сб 08:00–22:00; ",
    "70000001101682630": "телефон +992 888 00 00 11; WhatsApp: https://wa.me/992888000011; Telegram: https://t.me/+992888000011; Instagram: https://instagram.com/x_fitnesstj; часы: пн–пт 06:00–23:00, сб–вс 07:00–22:00; ",
    "70000001102665437": "контактов в карточке нет вовсе; часы: пн–сб 08:00–20:00; ",
    "70000001102714690": "телефон +992 018 78 48 48; WhatsApp: https://wa.me/992018784848; Instagram: https://instagram.com/falcongym_tj; часы: пн–сб 08:00–24:00; ",
    "70000001104949064": "телефон 985 70 06 06; мессенджеров и соцсетей в карточке нет; часы: пн–вс 07:00–23:00; ",
    "70000001101760246": "телефон +992 877 00 44 44; WhatsApp: https://wa.me/992877004444; Telegram: https://t.me/992877004444; Instagram: https://instagram.com/profit_dushanbe и https://instagram.com/profittajikistan; часы: пн–вс 07:00–23:00; ",
    "70000001101572228": "телефона в карточке нет, кнопка WhatsApp: https://wa.me/992905402222; Instagram: https://instagram.com/profittajikistan; часы: пн–вс 07:00–23:00; ",
    "70000001114088338": "телефон 908 55 65 65; WhatsApp: https://wa.me/992908556565; Instagram: https://instagram.com/_tajspa; часы: пн–вс 10:00–22:00; ",
    "70000001110965994": "телефоны +992 553 55 51 90 и 907 64 53 35; сайт записан как team.Boymurodov — домена с таким окончанием не существует, ошибка ввода в карточке; часы: пн–сб 07:00–23:00; ",
    "70000001103149258": "телефоны 944 77 00 55 и 947 77 00 55; Instagram: https://instagram.com/ufcgymtj; часы: пн–вс 07:00–23:00; ",
    "70000001100581600": "телефон 918 91 89 99; WhatsApp: https://wa.me/992918918999; Telegram: https://t.me/+992918918999; Instagram: https://instagram.com/garmonia.tjk; часы: пн–сб 08:00–22:00; ",
    "70000001101401151": "телефоны 918 24 36 24 и 900 07 44 44; WhatsApp: https://wa.me/992900074444; Instagram: https://instagram.com/fitnessclubumed1; часы: пн–вс 08:00–22:30; ",
    "70000001101958146": "телефон +992 446 60 55 55; Instagram: https://instagram.com/dorobgym.sozidanie; часы: пн–сб 07:00–23:00; ",
    "70000001109657173": "телефон +992 433 77 00 80; сайт http://dorobgym.tj/bukhoro; Instagram: https://instagram.com/dorobgym.bukhoro; Facebook: https://facebook.com/DorobGym; часы: пн–вс 08:00–23:00; ",
    "70000001101229632": "телефоны +992 883 06 26 26 и 981 08 00 01; WhatsApp: https://wa.me/992883062626; часы: пн–сб 04:00–23:00 (открытие в 4 утра выглядит как опечатка карточки, приведено дословно); ",
}

text = io.open(P, encoding="utf-8").read()
lines = text.split("\n")
hits = 0
for i, ln in enumerate(lines):
    s = ln.strip()
    if not s.startswith("- **") or "; карточка:" not in s:
        continue
    m = re.search(r"firm/(\d{6,})", s)
    if not m or m.group(1) not in INS:
        continue
    frag = INS.pop(m.group(1))
    marker = "; карточка:"
    pos = s.index(marker)
    lines[i] = s[:pos] + "; " + frag.rstrip() + " " + s[pos + 1:].lstrip()
    hits += 1

# --- переписать три пункта «Что осталось незакрытым» ---
REWRITES = [
    ("- **Яндекс: карточки + телефоны + остальные города.**",
     "- **Яндекс: карточки + остальные города.**"),
    ("Им закрывались ссылка на карточку Яндекс.Карт, обычные телефоны (`CompanyMetaData.contacts`) и города, которых нет в 2ГИС: Худжанд, Куляб, Бохтар и остальные.",
     "Им закрывались ссылка на карточку Яндекс.Карт и города, которых нет в 2ГИС: Худжанд, Куляб, Бохтар и остальные; телефоны отсюда выпали — они сняты с карточек 2ГИС вторым проходом."),
]
for old, new in REWRITES:
    if old in text:
        text = text.replace(old, new)
        print("rewrite ok:", old[:50])

# WhatsApp/Telegram пункт — заменить целиком по началу строки
wa_old_prefix = "- **WhatsApp/Telegram.** Ни 2ГИС, ни Яндекс поля"
wa_new = "- **WhatsApp/Telegram — частично закрыто карточками, остаток ручной.** Сами карточки 2ГИС знают кнопки WhatsApp и Telegram — это каналы, которые зал указал сам: из 19 кнопка WhatsApp стоит у 10, Telegram — у 5, все ссылки вписаны в список выше (в карточке X-FIT ссылка Telegram записана с ошибкой — см. строку). Для номеров без кнопки (8 залов с телефоном) привязка проверяется только вручную — открытием чата на `https://wa.me/<номер>` или поиском контакта в Telegram; ни один API такого поля не отдаёт. Этих проверок не выполнялось."
for i, ln in enumerate(lines):
    if ln.startswith(wa_old_prefix):
        lines[i] = wa_new
        print("wa item rewritten at line", i + 1)
        break

# Цены и часы работы пункт
pr_old_prefix = "- **Цены и часы работы.** В 2ГИС с демо-ключом их нет;"
pr_new = "- **Цены.** В 2ГИС их нет ни в API, ни на странице карточки; остаются Instagram-страницы залов (ссылки в списке выше у 15 из 19 карточек) и звонки — по образцу TODO-подраздела про банки в разделе 3. Часы работы сняты со страниц карточек у всех 19 залов и стоят в списке."
for i, ln in enumerate(lines):
    if ln.startswith(pr_old_prefix):
        lines[i] = pr_new
        print("prices item rewritten at line", i + 1)
        break

# применить REWRITES к уже собранному списку строк нельзя — текст менялся выше; собрать заново
out = "\n".join(lines)
for old, new in REWRITES:
    out = out.replace(old, new)

io.open(P, "w", encoding="utf-8", newline="\n").write(out)
print("hall lines patched:", hits, "| unpatched ids:", sorted(INS.keys()))
