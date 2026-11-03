# -*- coding: utf-8 -*-
"""Deterministic check of build/71_pokupki_chat.md (section 8a, chat block).

Two gates:
1. Quotes. Every «...» that carries an id must be found verbatim (word-level)
   inside the message of the (#id, date) that follows it; every cited id must
   exist and its date must match. Nested guillemets are handled by a depth
   counter, so «торговый центр «Садбарг»» is checked as one outer quote.
2. Ids. Every (#id, date) pair anywhere in the file must exist in the export
   and the date must match the message date.
Output goes to _verify_8a.txt (UTF-8); the console cannot print Cyrillic.
"""
import io
import os
import re
import json
import difflib

import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if len(sys.argv) > 1:
    SRC = os.path.abspath(sys.argv[1])
else:
    SRC = os.path.join(HERE, "..", "build", "71_pokupki_chat.md")
MSGS = os.path.join(HERE, "messages.jsonl")
OUT = os.path.join(
    HERE, "_verify_" + os.path.splitext(os.path.basename(SRC))[0] + ".txt")


def mdate_of(msg):
    """Дата сообщения в виде DD.MM.YYYY (корпус пишет день без ведущего нуля)."""
    raw = (msg.get("date") or u"").strip().split(u" ")[0]
    p = raw.split(u".")
    if len(p) == 3:
        try:
            return u"%02d.%02d.%s" % (int(p[0]), int(p[1]), p[2][:4])
        except ValueError:
            pass
    return raw


def load_msgs():
    msgs = {}
    with io.open(MSGS, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
                msgs[int(m.get("id"))] = m
            except Exception:
                continue
    return msgs


def norm(s):
    s = s.lower()
    s = s.replace(u"\u2014", u"-").replace(u"\u2013", u"-")
    s = s.replace(u"\u2026", u"...")
    s = re.sub(u"[\u00ab\u00bb\u201c\u201d\"]", u" ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def loose(s):
    return re.sub(u"[^0-9a-z\u0430-\u044f]+", u"",
                  norm(s).replace(u"\u0451", u"\u0435"))


def words(s):
    s = norm(s).replace(u"\u0451", u"\u0435")
    s = re.sub(u"(?<=[0-9])(?=[a-z\u0430-\u044f])", u" ", s)
    s = re.sub(u"(?<=[a-z\u0430-\u044f])(?=[0-9])", u" ", s)
    return re.findall(u"[0-9a-z\u0430-\u044f]+", s)


def frags(quote):
    quote = quote.replace(u"[\u0442\u0430\u043a]", u" ")
    parts = re.split(u"\u2026|\\.\\.\\.", quote)
    out = []
    for p in parts:
        p = p.strip(" .,!;:-")
        if len(loose(p)) >= 8:
            out.append(p)
    return out or [quote]


def best_ratio(frag, whole):
    a, b = words(frag), words(whole)
    if not a or not b:
        return 0.0, []
    if loose(frag) and loose(frag) in loose(whole):
        return 1.0, []
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    blocks = sm.get_matching_blocks()
    matched = sum(bl.size for bl in blocks)
    missing = []
    pos = 0
    for bl in blocks:
        if bl.a > pos:
            missing.extend(a[pos:bl.a])
        pos = bl.a + bl.size
    return matched / float(len(a)), missing


def extract_quotes(txt):
    """Outermost «...» spans, nesting-aware. Returns [(start, end, inner)]."""
    out = []
    stack = []
    for i, ch in enumerate(txt):
        if ch == u"\u00ab":
            stack.append(i)
        elif ch == u"\u00bb" and stack:
            st = stack.pop()
            if not stack:
                out.append((st, i + 1, txt[st + 1:i]))
    return out


def main():
    msgs = load_msgs()
    txt = io.open(SRC, "r", encoding="utf-8").read()
    out = []
    w = out.append

    w(u"messages loaded: %d" % len(msgs))
    w(u"file chars: %d, lines: %d" % (len(txt), len(txt.splitlines())))
    w(u"")

    # ---------- quotes ----------
    spans = extract_quotes(txt)
    checks = []
    for st, en, inner in spans:
        if len(inner) < 3:
            continue
        tail = txt[en:en + 260]
        cut = tail.find(u"\u00ab")
        if cut >= 0:
            tail = tail[:cut]
        if not re.search(r"#\d+", tail):
            checks.append((inner, [], u"no-id", st))
            continue
        paren = re.search(r"\(([^()]*#\d+[^()]*)\)", tail)
        if not paren:
            checks.append((inner, [], u"no-paren", st))
            continue
        group = paren.group(1)
        ids = []
        for mm in re.finditer(r"#(\d+)([^#]*)", group):
            dm = re.search(r"(\d{2}\.\d{2}\.\d{4})", mm.group(2))
            ids.append((int(mm.group(1)), dm.group(1) if dm else None))
        checks.append((inner, ids, u"ok", st))

    problems = []
    noquote = []
    shared = []
    total_ok = 0
    for quote, ids, flag, pos in checks:
        if flag != u"ok":
            if flag == u"no-id":
                noquote.append(quote)
                if len(quote) > 40:
                    ls = txt.rfind(u"\n", 0, pos) + 1
                    le = txt.find(u"\n", pos)
                    line = txt[ls:le if le > 0 else len(txt)]
                    line_ids = [int(x) for x in re.findall(r"#(\d+)", line)]
                    best = 0.0
                    lost = []
                    for mid in line_ids:
                        msg = msgs.get(mid)
                        if not msg:
                            continue
                        rs = [best_ratio(f, msg.get("text") or u"")
                              for f in frags(quote)]
                        worst = min(r for r, _ in rs)
                        if worst > best:
                            best = worst
                            lost = [ww for r, mm2 in rs if r < 0.995
                                    for ww in mm2]
                    if best < 0.85:
                        shared.append((quote, line_ids, best, lost))
            continue
        ok_here = False
        notes = []
        for mid, date in ids:
            msg = msgs.get(mid)
            if msg is None:
                notes.append(u"#%d MISSING MESSAGE" % mid)
                continue
            mdate = mdate_of(msg)
            if date and date != mdate:
                notes.append(u"#%d DATE %s != %s" % (mid, date, mdate))
            body = msg.get("text") or u""
            rs = [best_ratio(f, body) for f in frags(quote)]
            worst = min(r for r, _ in rs) if rs else 0.0
            lost = []
            for r, miss in rs:
                if r < 0.995:
                    lost.extend(miss)
            if worst >= 0.995:
                ok_here = True
            elif worst >= 0.85:
                ok_here = True
                notes.append(u"#%d CLOSE %.2f lost=%s"
                             % (mid, worst, u" ".join(lost[:12])))
            else:
                notes.append(u"#%d NOQUOTE %.2f lost=%s"
                             % (mid, worst, u" ".join(lost[:12])))
        if ok_here and not any(u"MISSING" in n or u"DATE " in n for n in notes):
            total_ok += 1
        if notes:
            problems.append((quote, ids, notes))

    w(u"quotes with ids: %d, fully ok: %d, problems: %d, quote w/o id: %d"
      % (len([c for c in checks if c[2] == u"ok"]), total_ok,
         len(problems), len(noquote)))
    w(u"")

    if noquote:
        w(u"--- quotes without a following id ---")
        for q in noquote:
            w(u"  %s" % q[:220])
        w(u"")

    for quote, ids, notes in problems:
        w(u"=== %s" % quote[:300])
        for mid, date in ids:
            msg = msgs.get(mid)
            if msg is None:
                w(u"    #%d  [no such message]  cited date=%s" % (mid, date))
                continue
            w(u"    #%d  cited=%s  real=%s  author=%s"
              % (mid, date, mdate_of(msg), msg.get("author")))
            w(u"      text: %s"
              % (msg.get("text") or u"")[:400].replace(u"\n", u" / "))
        for n in notes:
            w(u"    -> %s" % n)
        w(u"")

    w(u"--- long quotes (>40) resolved only against their own bullet ---")
    w(u"unresolved: %d" % len(shared))
    for quote, line_ids, best, lost in shared:
        w(u"  %.2f  %s" % (best, quote[:180]))
        w(u"        ids=%s lost=%s" % (line_ids, u" ".join(lost[:15])))
    w(u"")

    # ---------- all citation ids ----------
    missing = []
    baddate = []
    cited = set()
    for pm in re.finditer(r"\(([^()]*)\)", txt):
        body = pm.group(1)
        if not re.search(r"#\d+", body):
            continue
        for mm in re.finditer(r"#(\d+)([^#]*)", body):
            dm = re.search(r"(\d{2}\.\d{2}\.\d{4})", mm.group(2))
            cited.add((int(mm.group(1)), dm.group(1) if dm else None))
    for mid, date in sorted(cited, key=lambda x: (x[0], x[1] or u"")):
        if mid not in msgs:
            missing.append(mid)
            continue
        if date and date != mdate_of(msgs[mid]):
            baddate.append((mid, date, mdate_of(msgs[mid])))
    w(u"--- all citation ids ---")
    w(u"citation ids found: %d" % len(cited))
    w(u"ids not found in export: %s" % sorted(set(missing)))
    w(u"date mismatches: %d" % len(baddate))
    for mid, c, r in sorted(set(baddate)):
        w(u"    #%d cited=%s real=%s" % (mid, c, r))
    w(u"")

    io.open(OUT, "w", encoding="utf-8", newline=u"\n").write(
        u"\n".join(out) + u"\n")
    print("written %s (%d lines)" % (os.path.basename(OUT), len(out)))


if __name__ == "__main__":
    main()
