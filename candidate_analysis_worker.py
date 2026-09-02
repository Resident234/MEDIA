from __future__ import annotations

import argparse
import csv
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

UA = "Mozilla/5.0 (compatible; HabrCompaniesCandidateResearch/1.0)"
URL_RE = re.compile(r"<https?://[^>]+>")
MODEL = "gpt-5-mini"


def norm(text: str) -> str:
    return " ".join(text.casefold().replace("ё", "е").split())


def parse_urls(path: Path) -> list[str]:
    seen, urls = set(), []
    for raw in URL_RE.findall(path.read_text(encoding="utf-8")):
        url = raw[1:-1]
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def read_csv_values(path: Path, two_columns: bool = False) -> list[str]:
    values = []
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh):
            if not row:
                continue
            columns = row[:2] if two_columns else row[:1]
            values.extend(x.strip() for x in columns if x.strip())
    return values


def fetch_text(url: str, cache_dir: Path) -> dict:
    key = re.sub(r"[^A-Za-z0-9_.-]", "_", urlparse(url).path.strip("/") or "root")
    path = cache_dir / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    last_error = ""
    for attempt in range(3):
        try:
            response = requests.get(url, headers={"User-Agent": UA}, timeout=30)
            soup = BeautifulSoup(response.text, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            nodes = soup.select(
                "article.tm-article-presenter__content, .article-formatted-body, "
                ".tm-article-presenter__body, .tm-article-presenter__header, "
                ".tm-article-author__company, .tm-article-labels, .tm-article-presenter__meta"
            )
            if nodes:
                text = " ".join(node.get_text(" ", strip=True) for node in nodes)
            else:
                for node in soup(["script", "style", "noscript", "svg"]):
                    node.decompose()
                text = soup.get_text(" ", strip=True)
            result = {"url": url, "status": response.status_code, "title": title, "text": text}
            path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            return result
        except requests.RequestException as exc:
            last_error = str(exc)
            time.sleep(1.5 * (attempt + 1))
    result = {"url": url, "status": 0, "title": "", "text": "", "error": last_error}
    path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def load_results(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    results = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            results[item["url"]] = item
    return results


def load_known_records(path: Path) -> dict[str, tuple[str, str]]:
    records = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith("- https://") and index + 2 < len(lines):
            records[line[2:]] = (lines[index + 1], lines[index + 2])
    return records


def ask_candidates(client: OpenAI, article: dict, known_industries: list[str], known_companies: list[str]) -> dict:
    text = article.get("text", "")
    excerpt = text[:18000]
    if not excerpt:
        return {"industries": [], "companies": [], "reason": "article text unavailable"}
    schema = {
        "type": "object",
        "properties": {
            "industries": {"type": "array", "items": {"type": "string"}, "maxItems": 12},
            "companies": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
            "reason": {"type": "string"},
        },
        "required": ["industries", "companies", "reason"],
        "additionalProperties": False,
    }
    prompt = f"""Проанализируй текст статьи Habr и найди КАНДИДАТОВ на новые отрасли и компании.

Известные отрасли из CSV:
{', '.join(known_industries)}

Известные компании из CSV:
{', '.join(known_companies)}

Правила:
1. Верни только явно упомянутые в тексте статьи сущности, а не догадки по теме статьи.
2. В candidates industries включай устойчивые названия отраслей, сфер или рынков; не включай технологии, библиотеки, должности и общие слова вроде «разработка».
3. В candidates companies включай организации, бренды, продукты или сервисы, которые выглядят как названия компаний/организаций.
4. Исключи сущности, совпадающие с известными значениями CSV с учётом регистра, Ё/Е, кавычек и очевидных падежных форм.
5. Не включай авторов, пользователей, города и страны, если это не организация.
6. Сохрани написание так, как оно дано в статье; убери только лишние кавычки и пробелы.
7. Если достоверных кандидатов нет, верни пустые массивы.

Статья: {article.get('title', '')}
Текст:
{excerpt}"""
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "Ты строгий извлекатель сущностей. Отвечай только JSON по схеме."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_schema", "json_schema": {"name": "candidates", "strict": True, "schema": schema}},
                max_completion_tokens=1200,
            )
            data = json.loads(response.choices[0].message.content)
            return {
                "industries": sorted(set(x.strip() for x in data.get("industries", []) if x.strip()), key=norm),
                "companies": sorted(set(x.strip() for x in data.get("companies", []) if x.strip()), key=norm),
                "reason": data.get("reason", ""),
            }
        except Exception as exc:
            if attempt == 2:
                return {"industries": [], "companies": [], "reason": f"LLM error: {exc}"}
            time.sleep(2 * (attempt + 1))
    return {"industries": [], "companies": [], "reason": "unknown error"}


def write_report(path: Path, urls: list[str], known_records: dict[str, tuple[str, str]], results: dict[str, dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        fh.write("# Упоминания и кандидаты отраслей и компаний в статьях Habr\n\n")
        fh.write("Первые два поля в каждой записи — совпадения со справочниками; последние два поля — кандидаты, найденные при повторном анализе текста. Известные сущности исключены из кандидатов.\n\n")
        for url in urls:
            fh.write(f"- {url}\n")
            known = known_records.get(url)
            if known:
                fh.write(f"{known[0]}\n{known[1]}\n")
            else:
                fh.write("- Отрасли: не найдено\n- Компании: не найдено\n")
            item = results.get(url, {})
            candidates = item.get("candidates", {})
            industries = candidates.get("industries", []) or ["не найдено"]
            companies = candidates.get("companies", []) or ["не найдено"]
            fh.write(f"- Кандидаты отраслей: {', '.join(industries)}\n")
            fh.write(f"- Кандидаты компаний: {', '.join(companies)}\n\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parent)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=0)
    args = parser.parse_args()
    root = args.root
    urls = parse_urls(root / "habr_companies_bookmarks.md")
    target_urls = urls[args.start:args.start + args.count] if args.count else urls[args.start:]
    category_values = read_csv_values(root / "habr_companies_category.csv", two_columns=True)
    company_values = read_csv_values(root / "habr_companies_companies.csv")
    known_industries = sorted(set(category_values), key=norm)
    known_companies = sorted(set(company_values), key=norm)
    known = {"industries": {norm(x) for x in known_industries}, "companies": {norm(x) for x in known_companies}}
    cache_dir = root / ".candidate-cache"
    cache_dir.mkdir(exist_ok=True)
    state_path = root / "candidate_results.jsonl"
    report_path = root / "habr_companies_articles_entities.md"
    known_records = load_known_records(root / "habr_companies_articles_entities_known.md")
    results = load_results(state_path)
    client = OpenAI()
    for start in range(0, len(target_urls), args.batch_size):
        batch = [url for url in target_urls[start:start + args.batch_size] if url not in results]
        if not batch:
            continue
        articles = {}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(fetch_text, url, cache_dir): url for url in batch}
            for future in as_completed(futures):
                item = future.result()
                articles[item["url"]] = item
        with ThreadPoolExecutor(max_workers=min(args.workers, len(batch))) as pool:
            futures = {
                pool.submit(ask_candidates, client, articles[url], known_industries, known_companies): url
                for url in batch
            }
            for future in as_completed(futures):
                url = futures[future]
                candidates = future.result()
                candidates["industries"] = [x for x in candidates.get("industries", []) if norm(x) not in known["industries"]]
                candidates["companies"] = [x for x in candidates.get("companies", []) if norm(x) not in known["companies"]]
                results[url] = {"url": url, "status": articles[url].get("status", 0), "candidates": candidates}
                with state_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(results[url], ensure_ascii=False) + "\n")
        write_report(report_path, urls, known_records, results)
        processed = sum(1 for url in urls if url in results)
        print(f"processed {processed}/{len(urls)}; batch {args.start + start + len(batch)}/{args.start + len(target_urls)}", flush=True)


if __name__ == "__main__":
    main()
