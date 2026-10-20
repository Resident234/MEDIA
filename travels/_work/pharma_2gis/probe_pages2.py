# -*- coding: utf-8 -*-
"""Второй заход: корректные параметры SSR-выдачи и клиентский бэкенд 2ГИС.

usage: python probe_pages2.py

В прошлый прогон `?page=2` сервер честно проигнорировал (те же 12 id), а
варианты с `&center=` дали 404 только потому, что параметр приклеивался к URL
без вопросика. Здесь проверяются все оставшиеся способы получить из выдачи
больше первой страницы:

1. `?center=<lon,lat>&zoom=<z>` — привязка к видимой области. Если сервер
   честно её соблюдает, полный список собирается плитками;
2. разные `?zoom` над одним центром — меняется ли состав id;
3. `?page=2` против `?page=2` с `rubric_id` (выдача по рубрике, а не по тексту);
4. robots.txt и sitemap — у 2ГИС SEO-списки рубрик иногда бывают в карте сайта;
5. какие пути дёргает фронтенд (в бандле ищутся `/_/...`, `/api/...`,
   `apiv2`, `/catalog/`) — если это открытый путь с куками страницы, запрос
   можно повторять без ключа.

`total` для «аптеки» по Душанбе уже известен: 1084.
"""
import io
import json
import os
import re
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0"
CITY = "dushanbe"


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def fetch(url, referer=None):
    h = {"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.8"}
    if referer:
        h["Referer"] = referer
    req = urllib.request.Request(url, headers=h)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return resp.getcode(), resp.read().decode("utf-8", "replace")
    except Exception as exc:                       # noqa: BLE001
        return -1, repr(exc)[:160]


def ids_of(t):
    return set(re.findall(r"/%s/(?:firm|carid)/(\d{6,})" % CITY, t))


def q(text):
    return urllib.parse.quote(text.encode("utf-8"))


def main():
    base = "https://2gis.tj/%s/search/%s" % (CITY, q("аптеки"))
    out = {}

    def probe(name, url, need_ids=True):
        code, t = fetch(url, referer=base)
        row = {"code": code, "bytes": len(t)}
        if code == 200 and need_ids:
            row["ids"] = len(ids_of(t))
            row["total"] = sorted(set(re.findall(r'"total"\s*:\s*(\d+)', t)))[:4]
        elif code == 200:
            row["head"] = ascii_(t[:160])
        else:
            row["err"] = ascii_(t[:90])
        out[name] = row
        print("%-18s %s" % (name, ascii_(json.dumps(row, ensure_ascii=True))))
        return t

    print("=== центр/зум ===")
    sets = {}
    for name, cen, zm in [
            ("c_center_z12", "68.7864,38.5598", "12"),
            ("c_center_z14", "68.7864,38.5598", "14"),
            ("c_center_z16", "68.7864,38.5598", "16"),
            ("c_west_z15", "68.7400,38.5500", "15"),
            ("c_east_z15", "68.8400,38.5700", "15"),
            ("c_north_z15", "68.7800,38.6000", "15"),
            ("c_south_z15", "68.7800,38.5100", "15")]:
        url = base + "?center=" + cen + "&zoom=" + zm + "&sorting=by_relevance"
        t = probe(name, url)
        sets[name] = ids_of(t) if t else set()
    allids = set()
    for k, v in sets.items():
        allids |= v
    print("уникальных id по всем центрам/зумам:", len(allids))
    for k, v in sorted(sets.items()):
        print("  ", k, len(v))

    print("=== рубрика вместо текста ===")
    probe("rubric_id", base + "&rubric_id=207")
    probe("rubric_id_page2", base + "?rubric_id=207&page=2")
    probe("type_seo", "https://2gis.tj/%s/type/company" % CITY)
    probe("apteki_path", "https://2gis.tj/%s/search/%s" % (CITY, q("Аптеки")))
    probe("apteki_lat", "https://2gis.tj/%s/search/%s" % (CITY, q("apteka")))
    probe("doruhona", base.replace(q("аптеки"), q("дорухона")))
    probe("apteka_24", base.replace(q("аптеки"), q("аптека 24 часа")))

    print("=== robots/sitemap ===")
    for path in ("robots.txt", "sitemap.xml", "sitemaps/firms.xml"):
        probe(path.replace("/", "_"), "https://2gis.tj/" + path, need_ids=False)

    print("=== пути фронтенда из бандлов ===")
    hits = {}
    for s in re.findall(r'<script[^>]+src="([^"]+)"', io.open(
            os.path.join(HERE, "_probe_search_фармация.html"), encoding="utf-8").read()):
        url = s if s.startswith("http") else "https://2gis.tj" + s
        if "polyfills" in url:
            continue
        body = fetch(url)[1]
        for p in set(re.findall(r"[\"'`](/[A-Za-z0-9_.\-/]{3,40}(?:items|search|catalog|firm|rubric)[A-Za-z0-9_.\-/?=]{0,30})[\"'`]", body)):
            hits.setdefault(p, 0)
            hits[p] += 1
        for p in set(re.findall(r"[\"'`](2gis\.apiv2[A-Za-z0-9_./]{0,30}|items/[A-Za-z0-9_./]{0,20})[\"'`]", body)):
            hits.setdefault(p, 0)
            hits[p] += 1
    print(json.dumps(dict(sorted(hits.items(), key=lambda kv: -kv[1])[:40]),
                      ensure_ascii=True, indent=1))
    out["frontend_paths"] = hits
    io.open(os.path.join(HERE, "_pages2_probe.json"), "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=True, indent=1)[:200000])
    io.open(os.path.join(HERE, "_pages2_ids.json"), "w", encoding="utf-8").write(
        json.dumps({k: sorted(v) for k, v in sets.items()}))


if __name__ == "__main__":
    main()
