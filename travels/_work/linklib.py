# -*- coding: utf-8 -*-
"""Индекс «строка строки → URL-источник» для простановки ссылок в справочнике.

Источники сигналов:
  notes/<slug>.md  — строки-факты, у каждой есть URL в шапке файла (провенанс точный);
  raw/<slug>.json  — полный текст статьи окнами по ~3 предложения (широкий recall).
"""
import json
import math
import re
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
NOTES = BASE / "notes"
RAW = BASE / "raw"
LINKS = BASE / "sections" / "links.md"

STOP = set("""и во с на как что это для от до из по при все уже ещё не ни он она они его её мы вы ты
такой был была были есть очень один одна самой сам так но или ли же то тех этих тем этим том чем
какой какие мой наша наш их более менее который которая которые быть стало стал стала надо нужно
можно нельзя всего всех всем всю прям вообще просто действительно здесь там тут когда где куда
лет году года годы ты ся""".split())

TAG_RE = re.compile(r"`\[[^\]]*\]`|\(мнение автора[^)]*\)|`[^`]*`")
WORD_RE = re.compile(r"[а-яё0-9]+")
NUM_LINK_RE = re.compile(r"^(\d+)\.\s+<(https?://[^>]+)>")


def norm(s):
    return s.lower().replace("ё", "е")


def toks(s):
    out = []
    for w in WORD_RE.findall(norm(TAG_RE.sub(" ", s))):
        if w.isdigit():
            out.append(w)
        elif len(w) >= 4 and w not in STOP:
            out.append(w[:5])
    return out


def link_numbers():
    """URL -> номер в списке «Обработанные ссылки»."""
    m = {}
    for ln in LINKS.read_text(encoding="utf-8").splitlines():
        g = NUM_LINK_RE.match(ln.strip())
        if g:
            m.setdefault(g.group(2), int(g.group(1)))
    return m


def split_windows(text, max_chars=320):
    sents = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text))
    out, cur = [], ""
    for s in sents:
        if not s.strip():
            continue
        if len(cur) + len(s) > max_chars and cur:
            out.append(cur)
            cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur:
        out.append(cur)
    return out


class Index(object):
    def __init__(self):
        self.notes = defaultdict(list)   # url -> [(token_set, text)]
        self.raw = defaultdict(list)     # url -> [(token_set, text)]
        self.df = defaultdict(int)
        self.idf = {}
        self.n_units = 0
        self._build()

    def _add(self, bucket, url, text):
        t = toks(text)
        if len(t) < 2:
            return
        s = set(t)
        bucket[url].append((s, text))
        for w in s:
            self.df[w] += 1
        self.n_units += 1

    def _build(self):
        for f in sorted(NOTES.glob("*.md")):
            body = f.read_text(encoding="utf-8").splitlines()
            g = re.match(r"#\s*(\S+)", body[0])
            if not g:
                continue
            url = g.group(1)
            for ln in body:
                t = ln.strip()
                if not t.startswith("- "):
                    continue
                txt = re.sub(r"^-\s*(\[[A-Z_А-ЯЁ ]+\]\s*)*", "", t)
                self._add(self.notes, url, txt)
        bad = 0
        for f in sorted(RAW.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            url, text = d.get("url", ""), (d.get("text") or "")
            if not url or len(text) < 200:
                bad += 1
                continue
            for w in split_windows(text):
                self._add(self.raw, url, w)

    def finish_idf(self):
        n = max(1, self.n_units)
        self.idf = {w: math.log(1.0 + n / (1.0 + c)) for w, c in self.df.items()}

    def weight(self, s):
        return sum(self.idf.get(w, 0.0) for w in s) or 1e-9

    def best_for(self, q, urls=None):
        """q — token_set строки документа. Возвращает [(url, score, kind, snippet)]."""
        if not q:
            return []
        qw = self.weight(q)
        res = {}
        for kind, bucket, k in (("notes", self.notes, 1.0), ("raw", self.raw, 0.90)):
            for url, units in bucket.items():
                if urls is not None and url not in urls:
                    continue
                for s, txt in units:
                    inter = q & s
                    if not inter:
                        continue
                    cw = self.weight(q & s) / qw
                    jw = self.weight(q & s) / self.weight(q | s)
                    sc = (0.75 * cw + 0.25 * jw) * k
                    if url not in res or res[url][0] < sc:
                        res[url] = (sc, kind, txt)
        return sorted(((u, v[0], v[1], v[2]) for u, v in res.items()),
                      key=lambda x: -x[1])[:8]


if __name__ == "__main__":
    idx = Index()
    idx.finish_idf()
    print("sources: notes=%d raw=%d units=%d" % (len(idx.notes), len(idx.raw), idx.n_units))
    print("link numbers:", len(link_numbers()))
