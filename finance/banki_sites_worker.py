# -*- coding: utf-8 -*-
"""
banki_sites_worker.py — собирает все банки со страницы отзывов
https://www.banki.ru/services/responses/ (включая пагинацию ?page=N),
для каждого банка берет карточку https://www.banki.ru/banks/bank/<slug>/
и через LLM (локальный OpenAI-совместимый эндпоинт, конфиг finance/llm_endpoint.json)
извлекает домен официального сайта банка.

Результат: finance/banki_ru_bank_sites.md
Кэш (resumable, не коммитится): finance/_banki_work/

Запуск:  python -X utf8 finance/banki_sites_worker.py
"""
import html as html_mod
import json
import os
import re
import sys
import time
from urllib.parse import unquote, urlparse

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(BASE, "_banki_work")
os.makedirs(WORK, exist_ok=True)

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

# ---------------------------------------------------------------- config
with open(os.path.join(BASE, "llm_endpoint.json"), encoding="utf-8") as f:
    LLM = json.load(f)

HDRS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "ru-RU,ru;q=0.8",
}
sess = requests.Session()
sess.headers.update(HDRS)

BANK_LINK_RE = re.compile(r"/services/responses/bank/([a-z0-9_-]+)/")
AWAY_RE = re.compile(r'href="/away/\?url=([^"]+)"')
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)

SLEEP = 1.0


def get(url, tries=4):
    """GET with naive throttle + retry/backoff on timeouts/429/5xx."""
    r = None
    for i in range(tries):
        try:
            r = sess.get(url, timeout=40)
        except requests.exceptions.RequestException as e:
            print(f"[net] {url} attempt {i + 1}: {e.__class__.__name__}")
            time.sleep(4 * (i + 1))
            continue
        if r.status_code in (429, 500, 502, 503):
            time.sleep(5 * (i + 1))
            continue
        return r
    return r


def get_html(url):
    r = get(url)
    if r is None:
        return 0, "", url
    return r.status_code, r.content.decode("utf-8", "replace"), r.url


def deesc(s):
    r"""eventLabel приходит с \uXXXX-эскейпами в HTML — раскодируем"""
    if not s or "\\u" not in s:
        return s
    try:
        return json.loads('"' + s.replace('"', '\\"') + '"')
    except Exception:
        return s


def clean_text(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_mod.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def base_domain(host):
    host = (host or "").lower().strip().rstrip(".")
    for p in ("www.", "m."):
        if host.startswith(p):
            host = host[len(p):]
    return host


def reg_domain(d):
    """грубая registrable-доменная нормализация для сравнения"""
    d = base_domain(d)
    labels = d.split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else d


def host_from_url(u):
    u = unquote(u or "")
    if not u.startswith("http"):
        u = "https://" + u
    return base_domain(urlparse(u).netloc)


# ---------------------------------------------------------------- step A: list
def collect_list_slugs():
    """Пагинация отзывов; стоп когда страница не даёт новых ссылок на банки."""
    cache = os.path.join(WORK, "list_slugs.json")
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            return json.load(f)
    seen, ordered, names = set(), [], {}
    prev_set = None
    for page in range(1, 40):
        url = f"https://www.banki.ru/services/responses/?page={page}"
        code, h, _ = get_html(url)
        if code != 200:
            print(f"[list] page {page} HTTP {code}, stop")
            break
        slugs = set(BANK_LINK_RE.findall(h)) - {"response"}
        if slugs == prev_set:  # список исчерпан (дальше только ссылки из шапки/подвала)
            print(f"[list] page {page} repeats previous -> end")
            break
        prev_set = slugs
        # имена банков из gtm-разметки: "slug | Название | rank"
        for m in re.finditer(
                r'eventLabel&quot;:&quot;([a-z0-9_-]+) \| ([^|]+?) \| \d+&quot;', h):
            s, nm = m.group(1), m.group(2).strip()
            if s not in names and not s.isdigit():
                names[s] = deesc(nm)
        for s in sorted(slugs):
            if s not in seen:
                seen.add(s)
                ordered.append(s)
        print(f"[list] page {page}: {len(slugs)} slugs, total {len(ordered)}")
        time.sleep(SLEEP)
    out = {"slugs": ordered, "names": names}
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


def canonicalize(slug):
    """числовые/альтернативные slug приводим к каноническому через redirect"""
    cache_f = os.path.join(WORK, "canonical.jsonl")
    cache = {}
    if os.path.exists(cache_f):
        with open(cache_f, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                cache[d["slug"]] = d["canon"]
    if slug in cache:
        return cache[slug]
    try:
        code, _, final_url = get_html(f"https://www.banki.ru/services/responses/bank/{slug}/")
    except Exception as e:
        print(f"[canon] {slug} net fail: {e}")
        return slug
    m = re.search(r"/services/responses/bank/([a-z0-9_-]+)/", final_url)
    canon = m.group(1) if m and code == 200 else slug
    with open(cache_f, "a", encoding="utf-8") as f:
        f.write(json.dumps({"slug": slug, "canon": canon}) + "\n")
    time.sleep(SLEEP)
    return canon


# ---------------------------------------------------------------- step B: site
def llm_extract_site(name, slug, snippet):
    msg = [
        {"role": "system",
         "content": "Ты извлекаешь данные со страниц банка. Отвечай строго JSON."},
        {"role": "user",
         "content": (
             "Ниже фрагмент страницы банка сайта banki.ru (текст + ссылки). "
             f"Банк: {name!r} (код страницы: {slug}). "
             "Определи ДОМЕН официального сайта этого банка (например rshb.ru, "
             "sberbank.ru). Ссылки вида /away/?url=... ведут на внешние сайты — "
             "нужен именно официальный сайт банка, не банк.ру, не агрегатор, не соцсеть. "
             'Ответ: JSON {"domain": "домен или null"}')},
        {"role": "user", "content": snippet[:14000]},
    ]
    body = {"model": LLM.get("model", "auto"), "messages": msg, "temperature": 0}
    for attempt in range(3):
        try:
            r = requests.post(LLM["base_url"].rstrip("/") + "/chat/completions",
                              headers={"Authorization": f"Bearer {LLM['api_key']}"},
                              json=body, timeout=120)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            text = r.json()["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", text, re.S)
            d = json.loads(m.group(0)) if m else {}
            dom = d.get("domain")
            if dom:
                return base_domain(dom), text[:200]
            return "", text[:200]
        except Exception as e:
            print(f"[llm] {slug} attempt {attempt + 1}: {e}")
            time.sleep(3 * (attempt + 1))
    return None, "LLM_FAILED"


def process_bank(slug, name):
    url = f"https://www.banki.ru/banks/bank/{slug}/"
    code, h, _ = get_html(url)
    if code != 200:
        return {"slug": slug, "name": name,
                "card": url,
                "responses": f"https://www.banki.ru/services/responses/bank/{slug}/",
                "site": "", "error": f"card HTTP {code}"}
    # детерминированная истина: ссылка сразу после "Официальный сайт"
    gt = ""
    m = re.search(r"Официальный сайт.{0,6000}?/away/\?url=([^\"&]+)", h, re.S)
    if m:
        gt = host_from_url(m.group(1))
    else:
        m2 = AWAY_RE.search(h)
        if m2:
            gt = host_from_url(m2.group(1))
    # кандидаты для LLM: все /away/-ссылки с текстовым контекстом
    cands = []
    for m in AWAY_RE.finditer(h):
        ctx = clean_text(h[max(0, m.start() - 300):m.end() + 200])[:160]
        cands.append(f"- {unquote(m.group(1))[:120]} | контекст: {ctx}")
        if len(cands) >= 12:
            break
    if not cands:  # страниц без /away/ — ищем http(s) в тексте карточки
        for u in re.findall(r'https?://(?!www\.banki\.ru|banki\.ru|cdn\.)[^"\'\s<>]+', h)[:12]:
            cands.append(f"- {u[:120]}")
    snippet = "\n".join(cands) or "(нет внешних ссылок)"
    llm_dom, raw = llm_extract_site(name, slug, snippet)
    status = "ok"
    if llm_dom is None:
        final, status = gt, "llm_failed_use_regex"
    elif not llm_dom:
        final, status = gt, "llm_null" if gt else "none"
    elif gt and reg_domain(llm_dom) == reg_domain(gt):
        final = llm_dom
    elif gt:
        final, status = gt, f"MISMATCH llm={llm_dom}"
    else:
        final, status = llm_dom, "llm_only"
    return {"slug": slug, "name": name, "card": url,
            "responses": f"https://www.banki.ru/services/responses/bank/{slug}/",
            "site": final, "regex_gt": gt, "status": status, "llm_raw": raw}


def names_get(data, slug):
    return data.get("names", {}).get(slug, "")


def main():
    data = collect_list_slugs()
    names = data["names"]
    print(f"[list] уникальных slug: {len(data['slugs'])}")

    # канонизация только числовых slug (именованные из списка уже канонические,
    # это экономит ~150 запросов и не провоцирует троттлинг banki.ru);
    # 404 карточки обрабатывается fallback-редиректом ниже
    uniq, order = {}, []
    for s in data["slugs"]:
        c = canonicalize(s) if s.isdigit() else s
        if c not in uniq:
            uniq[c] = names.get(s, names.get(c, c))
            order.append(c)
        elif not uniq[c] or uniq[c] == s:
            uniq[c] = names.get(s, uniq[c])
        if c != s:
            print(f"[canon] {s} -> {c}")
    print(f"[canon] уникальных банков: {len(order)}")

    cache_f = os.path.join(WORK, "sites.jsonl")
    done = {}
    if os.path.exists(cache_f):
        with open(cache_f, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                done[d["slug"]] = d
    results = []
    for i, slug in enumerate(order, 1):
        if slug in done and done[slug].get("status") not in (None, "card_failed"):
            results.append(done[slug])
            continue
        try:
            r = process_bank(slug, uniq[slug])
            # fallback: 404 карточки -> канонический slug через редирект страницы отзывов
            if str(r.get("error", "")).startswith("card HTTP 404"):
                c = canonicalize(slug)
                if c != slug:
                    uniq[c] = uniq[c] or uniq[slug] or names_get(data, slug)
                    if c not in done:
                        r = process_bank(c, uniq.get(c) or slug)
                        r.setdefault("slug", c)
                        slug = c
        except Exception as e:
            print(f"[bank] {slug} failed: {e}")
            r = {"slug": slug, "name": uniq[slug], "card": 
                 f"https://www.banki.ru/banks/bank/{slug}/",
                 "responses": f"https://www.banki.ru/services/responses/bank/{slug}/",
                 "site": "", "status": "card_failed"}
        with open(cache_f, "a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        results.append(r)
        print(f"[{i}/{len(order)}] {slug}: {r.get('site')!r} ({r.get('status')})")
        time.sleep(SLEEP)

    write_md(results)
    mism = [r for r in results if str(r.get("status", "")).startswith("MISMATCH")]
    print(f"\nГотово: банков {len(results)}, расхождений LLM/regex: {len(mism)}")


def write_md(results):
    path = os.path.join(BASE, "banki_ru_bank_sites.md")
    ts = time.strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Банки со страницы отзывов banki.ru — ссылки на официальные сайты",
        "",
        f"Источник списка: <https://www.banki.ru/services/responses/> (включая пагинацию `?page=N`), {ts}.",
        "Домен официального сайта извлечён LLM из карточки `https://www.banki.ru/banks/bank/<slug>/`",
        "и сверен с детерминированной ссылкой «Официальный сайт» (`/away/?url=...`) на той же странице.",
        "",
        "| Банк | Отзывы на banki.ru | Карточка банка | Официальный сайт |",
        "|---|---|---|---|",
    ]

    def esc(x):
        return (x or "").replace("|", "\\|")

    for r in sorted(results, key=lambda x: (x.get("name") or x["slug"]).lower()):
        site = r.get("site") or ""
        site_md = f"[{esc(site)}](https://{esc(site)}/)" if site else "—"
        resp = r.get("responses") or f"https://www.banki.ru/services/responses/bank/{r['slug']}/"
        card = r.get("card") or f"https://www.banki.ru/banks/bank/{r['slug']}/"
        lines.append(f"| {esc(deesc(r.get('name')))} | [отзывы]({resp}) | "
                     f"[карточка]({card}) | {site_md} |")
    nogc = [r for r in results if not r.get("site")]
    lines += ["", f"Всего банков: {len(results)}; без найденного сайта: {len(nogc)}.", ""]
    noted = [r for r in results if r.get("note")]
    if noted:
        lines += ["## Примечания", ""]
        for r in sorted(noted, key=lambda x: (x.get("name") or x["slug"]).lower()):
            lines.append(f"- **{deesc(r.get('name')) or r['slug']}** ({r['slug']}): {r['note']}")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("[md]", path)


if __name__ == "__main__":
    main()
