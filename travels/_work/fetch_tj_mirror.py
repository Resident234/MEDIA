from __future__ import annotations

import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

import fetch_articles as fa

MIRROR_PATHS = {
    "/list/cinema-travel/": "/list/cinema-travel/",
    "/kyrgyzstan-tadzhikistan-trip/": "/kyrgyzstan-tadzhikistan-trip/",
    "/photoalbum-tadzhikistan/": "/photoalbum-tadzhikistan/",
    "/tadzhikistan-entry-rules/": "/tadzhikistan-entry-rules/",
    "/photoalbum-pamir-tract/": "/photoalbum-pamir-tract/",
    "/iskanderkul-lake/": "/iskanderkul-lake/",
    "/dushanbe/": "/dushanbe/",
}


def main() -> None:
    orig = []
    for f in fa.RAW.glob("*.json"):
        rec = json.loads(f.read_text(encoding="utf-8"))
        if "journal.tinkoff.ru" in rec["url"]:
            orig.append((f, rec))
    for path, rec in sorted(orig, key=lambda x: x[1]["url"]):
        m = re.match(r"https://journal\.tinkoff\.ru(/.*)$", rec["url"])
        if not m:
            continue
        mirror = "https://t-j.ru" + m.group(1)
        try:
            resp = requests.get(mirror, headers={"User-Agent": fa.UA}, timeout=60)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            for bad in soup.find_all(["script", "style", "noscript", "svg"]):
                bad.decompose()
            title = soup.title.get_text(strip=True) if soup.title else ""
            text = fa.pick(soup)
            text = re.sub(r"\n{3,}", "\n\n", text)
        except Exception as exc:  # noqa: BLE001
            print("FAIL", mirror, type(exc).__name__, str(exc)[:120])
            continue
        if len(text) < 800:
            print("TOO SHORT", resp.status_code, mirror, len(text), title)
            continue
        rec["mirror"] = mirror
        rec["mirror_status"] = resp.status_code
        rec["title"] = title
        rec["text"] = text
        path.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        print("OK", resp.status_code, len(text), "|", title[:90], "|", mirror)


if __name__ == "__main__":
    main()
