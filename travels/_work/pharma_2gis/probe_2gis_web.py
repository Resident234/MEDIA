# -*- coding: utf-8 -*-
"""Разведка: можно ли снять список аптек Душанбе с сайта 2ГИС без API.

usage: python probe_2gis_web.py

Демо-ключ API заблокирован (`403 apiKeyIsBlocked`), поэтому канал сбора
карточек organization остаётся только веб: страница карточки через SSR уже
работает (shops_2gis/ssr_pages/), а вот отдаёт ли серверную выдачу сам сайт
по адресу /dushanbe/search/<запрос> — проверялось один раз в жизни, в
прошлом прогоне за этим не ходили. Скрипт качает выдачу и печатает всё, что
определяет дальнейшую стратегию:

1. сколько ссылок на карточки в HTML и есть ли среди них id организаций;
2. есть ли на странице JSON состояния (данные выдачи обычно лежат в нём);
3. какой API ключ и какой endpoint использует сам фронтенд (из <script src>
   и из текста страницы) — Site-ключ 2ГИС обычно тот же демо-ключ, но на
   веб-домене он может быть другим;
4. видна ли пагинация (page=, _pN, «Показать ещё») — без неё список
   ограничен первой страницей, и тогда весь массив придётся добираать
   рубриками/плитками через тот же веб;
5. не ушло ли запрос в капчу.

Ответ печатается ASCII-escaped: консоль Windows в cp866 падает на кириллице.
"""
import io
import json
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0"
QUERIES = ["аптеки", "аптека", "дорухона", "фармация"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "ru-RU,ru;q=0.8"})
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return resp.getcode(), resp.read().decode("utf-8", "replace")
    except Exception as exc:                       # noqa: BLE001
        return -1, repr(exc)[:200]


def main():
    report = {}
    for q in QUERIES:
        url = ("https://2gis.tj/dushanbe/search/" +
               urllib.parse.quote(q.encode("utf-8")))
        code, t = get(url)
        row = {"url": url, "code": code, "bytes": len(t)}
        if code != 200:
            row["error"] = t[:150]
            report[q] = row
            continue
        path = os.path.join(HERE, "_probe_search_%s.html" % q)
        io.open(path, "w", encoding="utf-8").write(t)
        ids = re.findall(r"/dushanbe/(?:firm|carid)/(\d{6,})", t)
        row["firm_links"] = len(set(ids))
        row["ids_sample"] = sorted(set(ids))[:5]
        row["state_markers"] = [m for m in ("__INITIAL_STATE__", "window.__data",
                                            "NEXT_DATA", "application/ld+json",
                                            "DGTL_STATE", "items\":")
                                if m in t]
        row["ldjson_blocks"] = len(re.findall(r'<script[^>]*type="application/ld\+json"', t))
        row["captcha"] = bool(re.search(r"captcha|robot", t[:6000], re.I))
        row["api_keys"] = sorted(set(re.findall(
            r"[\"\']key[\"\']\s*[:=]\s*[\"\']([0-9a-f]{8}-[0-9a-f\-]{20,})", t)))[:6]
        row["api_hosts"] = sorted(set(re.findall(
            r"https?://[a-z0-9.\-]*api[a-z0-9.\-]*2gis[a-z.]*/[a-z0-9/._\-]{0,40}", t)))[:8]
        row["scripts"] = re.findall(r'<script[^>]+src="([^"]+)"', t)[:8]
        row["paging"] = sorted(set(re.findall(
            r"(?:page=|_p)\d+|nextPage|showMore|item-page|\d+\s*/\s*\d+", t)))[:8]
        # сколько карточек реально подписано на странице — по названию+адресу
        row["snippet_titles"] = len(re.findall(r'"title"\s*:\s*"', t))
        row["addresses"] = len(re.findall(r'"address_name"\s*:\s*"', t))
        report[q] = row
    print(json.dumps(report, ensure_ascii=True, indent=1))


if __name__ == "__main__":
    import urllib.parse                                  # noqa: E402
    main()
