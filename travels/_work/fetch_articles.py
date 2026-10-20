from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parent
RAW = BASE / "raw"
RAW.mkdir(parents=True, exist_ok=True)

SHEET = Path(r"C:\Users\GSU\AppData\Local\Temp\asia.csv")
ROW_FROM, ROW_TO = 206, 236  # блок «Таджикистан» на листе «Средняя Азия»

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

SKIP_HOSTS = {"ru.skyscanner.com", "t.me"}

SELECTORS = [
    ".aentry-post__text",
    "article",
    "main article",
    ".article__body",
    ".post__content",
    ".text__content",
    "#content",
    "main",
]


def sheet_urls() -> list[tuple[int, int, str]]:
    rows = list(csv.reader(io.StringIO(SHEET.read_text(encoding="utf-8"))))
    out, seen = [], set()
    for ri in range(ROW_FROM, ROW_TO + 1):
        for ci, cell in enumerate(rows[ri]):
            for url in re.findall(r"https?://[^\s\"\\<>]+", cell):
                url = url.rstrip(".,;)")
                if url in seen:
                    continue
                seen.add(url)
                out.append((ri, ci, url))
    return out


def pick(soup: BeautifulSoup) -> str:
    for sel in SELECTORS:
        node = soup.select_one(sel)
        if node:
            for bad in node.select("script, style, noscript, svg, form, .comment, .comments, .lj-comments"):
                bad.decompose()
            text = node.get_text("\n", strip=True)
            if len(text) > 400:
                return text
    for bad in soup.find_all(["script", "style", "noscript", "svg"]):
        bad.decompose()
    return soup.get_text("\n", strip=True)


def slug(url: str) -> str:
    host = re.sub(r"^www\.", "", urlparse(url).netloc)
    return f"{host}__{hashlib.md5(url.encode()).hexdigest()[:10]}"


def fetch(url: str) -> dict:
    path = RAW / (slug(url) + ".json")
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    rec = {"url": url, "status": "", "title": "", "text": "", "error": ""}
    last = ""
    for attempt in range(3):
        try:
            resp = requests.get(url, headers={"User-Agent": UA}, timeout=60, allow_redirects=True)
            rec["status"] = resp.status_code
            if resp.status_code != 200:
                last = f"http {resp.status_code}"
                time.sleep(2 + attempt * 3)
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            title = soup.title.get_text(strip=True) if soup.title else ""
            rec["title"] = title
            text = pick(soup)
            text = re.sub(r"\n{3,}", "\n\n", text)
            rec["text"] = text
            break
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(2 + attempt * 3)
    rec["error"] = last
    path.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    return rec


def main() -> None:
    items = sheet_urls()
    log = []
    for ri, ci, url in items:
        host = urlparse(url).netloc
        if any(h in host for h in SKIP_HOSTS):
            log.append(f"SKIP  {url}")
            continue
        rec = fetch(url)
        log.append(
            f"R{ri}C{ci} {rec['status']} len={len(rec['text']):>6} err={rec['error'][:60]:60} {url}"
        )
        print(log[-1], flush=True)
    (BASE / "fetch_log.txt").write_text("\n".join(log), encoding="utf-8")


if __name__ == "__main__":
    main()
