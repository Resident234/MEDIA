# -*- coding: utf-8 -*-
"""Resumable per-domain Google Maps collector.

usage: python run_domain.py <plan.tsv> <outdir> [--cards]

Plan TSV columns (tab-separated, no header, lines starting with # ignored):
    slug<TAB>near<TAB>query[;query2;...]
Where `near` is `lat,lon` (feeds the `/@lat,lon,14z/` hint so small towns
resolve to their own catalog), or empty for a plain text-only search.

For every (city, query) row the script:
  1. Opens the Google Maps search URL and scrolls the virtualized feed to
     bottom, harvesting unique place cards by Google feature id.
  2. Appends rows to <outdir>/rows.jsonl and writes <outdir>/<slug>__<qn>.ok
     on success so a rerun skips it.
  3. If --cards is passed, for every harvested row that has no cached card
     JSON at <outdir>/cards/<fid_slug>.json, opens the place page and dumps
     the extracted contact dict.

The script never dies on transient failures: on captcha / missing feed it
logs a warning and leaves the .ok absent so the next run retries it.
"""
import argparse
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ggd


def _force_utf8_stdio():
    """Force UTF-8 on stdout/stderr so the collectors don't crash.

    The Windows console/pipe for a redirected child defaults to cp866/cp1251,
    which cannot encode Tajik-Cyrillic query/place glyphs (e.g. '\u04b6' Ҷ,
    '\u04b3' ѳ, '\u04b7' ҷ). A bare `print()` of those raised
    UnicodeEncodeError and killed the lists/cards phases (rc=1). Rows and card
    JSON are already written as UTF-8 files; only the console echo broke, so we
    reconfigure the text streams here. `-X utf8` alone did NOT reliably help
    once stdout is a redirected pipe, so we do it in-process.
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            try:
                buf = getattr(stream, "buffer", None)
                if buf is not None:
                    setattr(sys, name, io.TextIOWrapper(
                        buf, encoding="utf-8", errors="replace",
                        line_buffering=True))
            except Exception:
                pass


_force_utf8_stdio()


def slugify(s):
    s = re.sub(r"[^0-9A-Za-z\u0400-\u04FF_-]+", "_", s.strip())
    return s[:80].strip("_") or "x"


def load_plan(path):
    rows = []
    for line in io.open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        slug = parts[0]
        near = parts[1] if len(parts) > 1 else ""
        qs = parts[2] if len(parts) > 2 else parts[1]
        for q in [x.strip() for x in qs.split(";") if x.strip()]:
            rows.append((slug, near, q))
    return rows


def read_rows(path):
    out = {}
    if not os.path.exists(path):
        return out
    for line in io.open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        out[r.get("fid")] = r
    return out


def append_rows(path, rows):
    with io.open(path, "a", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def collect_lists(plan_path, outdir):
    os.makedirs(outdir, exist_ok=True)
    rows_path = os.path.join(outdir, "rows.jsonl")
    existing = read_rows(rows_path)
    rows_seen = set(existing.keys())
    print("seed rows=%d" % len(rows_seen), flush=True)
    for slug, near, q in load_plan(plan_path):
        qn = slugify(q)
        ok = os.path.join(outdir, "%s__%s.ok" % (slug, qn))
        if os.path.exists(ok):
            print("[skip ok] %s / %s" % (slug, q), flush=True)
            continue
        url = ggd.search_url(q, city=None, near=near or None)
        if near:
            print("  url=%s" % url[:120], flush=True)
        data = ggd.search(url)
        if data is None:
            print("  FAIL no-harvest %s / %s" % (slug, q), flush=True)
            time.sleep(30)
            continue
        new = []
        for it in data.get("items", []):
            if it["fid"] in rows_seen:
                continue
            rows_seen.add(it["fid"])
            it["city_slug"] = slug
            it["query"] = q
            new.append(it)
        if new:
            append_rows(rows_path, new)
        with io.open(ok, "w", encoding="utf-8") as fh:
            fh.write("count=%d new=%d url=%s\n" % (data.get("count", 0), len(new), url))
        print("  %s / %s: total=%d new=%d" % (slug, q, data.get("count", 0), len(new)), flush=True)
        time.sleep(15)


def collect_cards(outdir):
    cards_dir = os.path.join(outdir, "cards")
    os.makedirs(cards_dir, exist_ok=True)
    rows = list(read_rows(os.path.join(outdir, "rows.jsonl")).values())
    print("cards targets=%d" % len(rows), flush=True)
    okc = bad = 0
    for r in rows:
        fpath = os.path.join(cards_dir, slugify(r["fid"]) + ".json")
        if os.path.exists(fpath):
            okc += 1
            continue
        d = ggd.card(r["href"])
        if d is None:
            print("  FAIL card %s" % r["href"][:80], flush=True)
            bad += 1
            time.sleep(30)
            continue
        d["fid"] = r["fid"]
        d["name"] = d.get("name") or r.get("name")
        d["list_href"] = r["href"]
        d["city_slug"] = r.get("city_slug")
        d["query"] = r.get("query")
        io.open(fpath, "w", encoding="utf-8").write(
            json.dumps(d, ensure_ascii=False, indent=1))
        okc += 1
        print("  ok card %s (%s)" % (r["fid"][:20], (d.get("name") or "")[:40]), flush=True)
        time.sleep(12)
    print("cards done ok=%d failed=%d" % (okc, bad), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("outdir")
    ap.add_argument("--cards", action="store_true")
    ap.add_argument("--lists-only", action="store_true")
    ap.add_argument("--cards-only", action="store_true")
    args = ap.parse_args()
    ggd.warm()
    if not args.cards_only:
        collect_lists(args.plan, args.outdir)
    if (args.cards or args.cards_only) and not args.lists_only:
        collect_cards(args.outdir)


if __name__ == "__main__":
    main()
