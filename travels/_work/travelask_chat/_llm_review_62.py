# -*- coding: utf-8 -*-
"""_llm_review_62.py — LLM-перепроверка части 7c «Алкоголь».

Режимы:
  facts — по каждому подразделу черновика 62_alc.md отдаёт модели сам текст
          и полные тексты всех процитированных сообщений: ищет утверждения,
          которых в цитатах нет, приписанные не тому номеру, обобщения;
  gaps  — отдаёт модели сообщения чата про алкоголь, которые в часть не попали,
          и спрашивает, какие существенные факты (адрес, название, цена,
          правило) стоит добавить.

Обе проверки можно гонять разными моделями: находки, которые видят обе,
считаем сильным сигналом.

Запуск: python _llm_review_62.py facts  <model>
       python _llm_review_62.py gaps   <model>
"""
import io
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

import triage

HERE = os.path.dirname(os.path.abspath(__file__))
DRAFT = os.path.join(HERE, "..", "build", "62_alc.md")
MSGS = os.path.join(HERE, "messages.jsonl")
RAW = os.path.join(HERE, "_llm_alc_review.jsonl")

ALCO = re.compile(
    u"(?i)(алкогол|спиртн|пив|пивовар|винзавод|винодел|вино|вина|водк|коньяк"
    u"|виски|джин|шампанск|крафт|разливн|пивнуш|\\bбар\\b|\\bбары\\b|\\bбаров\\b"
    u"|паб|дьюти|беспошлин|алкомаркет|алкомагазин|градус|кеклик|шохона"
    u"|суммит|summit|подвал)")

# блоки-метаутверждения о корпусе: их проверяет не модель, а пересчёт по экспорту
META_BLOCKS = (u"Чего в чате нет", u"Оговорки по разделу")

GROUPS = (
    (u"ПИВО И ПИВЗАВОДЫ",
     re.compile(u"(?i)(пив|пивовар|завод|крафт|ipa|разлив|сим.?сим|лучоб)")),
    (u"ГДЕ ПРОДАЁТСЯ",
     re.compile(u"(?i)(куп|магазин|прода|алкомаркет|алкомагазин|дьюти|беспошлин"
                u"|супермаркет|ашан|bi1|пайкар|градус|gradys|red.?white"
                u"|красное|винзавод|рынок|базар)")),
    (u"БАРЫ",
     re.compile(u"(?i)(\\bбар\\b|\\bбары\\b|\\bбаров\\b|паб|пивнуш|кальян"
                u"|бундес|паблик|манкиз|монкиз|обезьян)")),
)

FACTS_PROMPT = u"""Ты проверяешь факты в путеводителе по Таджикистану.
Ниже фрагмент раздела «Алкоголь» и полные тексты сообщений чата, на которые он
ссылается. Номер в тексте (#1234) указывает на сообщение с тем же номером.

Правила чтения:
- фрагмент в «...» с пометкой (#номер, дата) — цитата из этого сообщения;
- ссылки вида [->28] ведут на статьи, их правильность НЕ проверяй;
- фразы без цитат — вывод автора раздела из цитат вокруг них.

Ищи только настоящие ошибки:
- утверждение, которого в сообщении нет (домысел, додуманная деталь);
- факт, приписанный не тому номеру (в сообщении он о другом городе, бренде,
  заведении);
- цена, адрес или название, которых в сообщении нет;
- вывод, который цитаты не поддерживают (например, «все», «везде», «никогда»,
  когда в сообщениях лишь один случай).

Не придирайся к стилю, длине абзацев, орфографии и к тому, что часть выводов
помечена как «мнение чата».

Ответ — строго JSON-массив объектов, без текста вокруг:
[{"draft": "фраза из черновика, до 120 символов",
  "problem": "в чём ошибка, до 120 символов",
  "id": номер сообщения или null}]
Если ошибок нет — [].

ЧЕРНОВИК:
%s

СООБЩЕНИЯ:
%s
"""

GAPS_PROMPT = u"""Ты редактор путеводителя по Таджикистану. Раздел «Алкоголь» уже
написан. Ниже его структура и сообщения чата, которые в него НЕ попали.

Выбери только те сообщения, которые добавляют существенный факт, которого в
разделе нет: адрес или название магазина, бара, завода; цену; правило продажи
или ввоза; название местного алкоголя; город. Эмоции, вопросы без ответа и
повторы не бери.

Ответ — строго JSON-массив объектов, без текста вокруг:
[{"id": номер сообщения, "fact": "что добавляет, до 140 символов"}]
Не более 10 объектов. Если добавлять нечего — [].

СТРУКТУРА РАЗДЕЛА:
%s

СООБЩЕНИЯ:
%s
"""


def a(s):
    print(s.encode("ascii", "replace").decode("ascii"))


def call(model, prompt, max_tokens=1800, tries=3):
    """Один явный вызов модели с повторами; возвращает текст ответа."""
    last = u""
    for attempt in range(tries):
        try:
            r = requests.post(
                triage.API_URL,
                headers={"Authorization": "Bearer " + triage.key(),
                         "Content-Type": "application/json"},
                json={"model": model, "temperature": 0, "max_tokens": max_tokens,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=420,
            )
            if r.status_code == 200:
                j = r.json()
                out = ((j.get("choices") or [{}])[0].get("message") or {}).get("content") or u""
                if out.strip():
                    return out
                last = u"empty content"
            else:
                last = u"HTTP %d %s" % (r.status_code, r.text[:120])
        except Exception as exc:                       # noqa: BLE001
            last = u"%s: %s" % (type(exc).__name__, str(exc)[:120])
        time.sleep(4 * (attempt + 1))
    raise RuntimeError(last)


def last_json_array(txt):
    """Последний сбалансированный JSON-массив: reasoning-модели пишут прозу до него."""
    t = txt.strip()
    t = re.sub(r"^```[a-zA-Z]*|```$", u"", t).strip()
    best = None
    depth = 0
    start = None
    for i, ch in enumerate(t):
        if ch == u"[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == u"]" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                chunk = t[start:i + 1]
                try:
                    parsed = json.loads(chunk)
                except ValueError:
                    continue
                if isinstance(parsed, list):
                    best = parsed
    return best


def load_msgs():
    d = {}
    with io.open(MSGS, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            d[r["id"]] = r
    return d


def msg_line(r, limit=700):
    t = re.sub(r"\s+", u" ", r.get("text") or u"")[:limit]
    rt = r.get("reply_to")
    ctx = u" (в ответ на #%s)" % rt if rt else u""
    return u"#%d [%s] %s%s: %s" % (r["id"], r.get("date") or u"?",
                                   r.get("author") or u"?", ctx, t)


def chunks(text, maxlen=7000):
    """Подразделы '###'; длинные дополнительно режем по '####'."""
    parts = []
    cur = [u"ВСТУПЛЕНИЕ", []]
    for line in text.splitlines():
        if line.startswith(u"### "):
            parts.append(cur)
            cur = [line[4:].strip(), []]
        else:
            cur[1].append(line)
    parts.append(cur)

    out = []
    for head, lines in parts:
        body = u"\n".join(lines).strip()
        if not body or head.startswith(META_BLOCKS):
            continue
        if len(body) <= maxlen:
            out.append((head, body))
            continue
        subs = []
        sub = [head, []]
        for line in lines:
            if line.startswith(u"#### "):
                subs.append(sub)
                sub = [head + u" / " + line[5:].strip(), []]
            else:
                sub[1].append(line)
        subs.append(sub)
        for name, ls in subs:
            b = u"\n".join(ls).strip()
            if b:
                out.append((name, b))
    return out


def cmd_facts(model, workers=3):
    text = io.open(DRAFT, encoding="utf-8").read()
    msgs = load_msgs()
    items = chunks(text)
    a("chunks: %d" % len(items))
    lock = threading.Lock()
    results = []

    def one(item):
        head, body = item
        ids = []
        for x in re.findall(r"#(\d+)", body):
            i = int(x)
            if i in msgs and i not in ids:
                ids.append(i)
        lines = [msg_line(msgs[i]) for i in ids]
        prompt = FACTS_PROMPT % (body, u"\n".join(lines))
        t0 = time.time()
        try:
            txt = call(model, prompt)
            arr = last_json_array(txt)
            if arr is None:
                arr, note = [], u"NO-JSON"
            else:
                note = u"ok"
        except Exception as exc:                       # noqa: BLE001
            arr, note, txt = [], u"ERROR %s" % str(exc)[:120], u""
        with lock:
            results.append({"block": head, "ids": len(ids), "model": model,
                            "note": note, "findings": arr, "raw": txt[:4000]})
            a("facts %-34s ids=%3d %-6s %2d findings %3.0fs"
              % (head[:34].encode("ascii", "replace").decode("ascii"),
                 len(ids), note[:6], len(arr), time.time() - t0))
        return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, items))

    order = [h for h, _ in items]
    results.sort(key=lambda r: order.index(r["block"]))
    with io.open(RAW, "a", encoding="utf-8", newline=u"\n") as f:
        for r in results:
            f.write(json.dumps(dict(r, pass_="facts"), ensure_ascii=False) + u"\n")

    slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
    out_path = os.path.join(HERE, "_llm_alc_facts_%s.txt" % slug)
    out = [u"model: %s" % model, u""]
    total = 0
    for r in results:
        if not r["findings"]:
            continue
        total += len(r["findings"])
        out.append(u"=== %s  [ids=%d]" % (r["block"], r["ids"]))
        for f in r["findings"]:
            if not isinstance(f, dict):
                out.append(u"  ? %s" % f)
                continue
            out.append(u"  ЧЕРНОВИК: %s" % f.get("draft", u""))
            out.append(u"  ПРОБЛЕМА: %s  => #%s"
                       % (f.get("problem", u""), f.get("id")))
            out.append(u"")
    bad = [r for r in results if r["note"] != u"ok"]
    out.insert(2, u"chunks: %d, findings: %d, failed chunks: %d"
               % (len(results), total, len(bad)))
    io.open(out_path, "w", encoding="utf-8", newline=u"\n").write(u"\n".join(out))
    a("facts: %d chunks, %d findings, %d failed -> %s"
      % (len(results), total, len(bad), os.path.basename(out_path)))
    return 0


def outline(text):
    keep = []
    short = False
    for line in text.splitlines():
        if line.startswith(u"### Коротко"):
            short = True
            keep.append(line)
            continue
        if line.startswith(u"### ") or line.startswith(u"#### "):
            keep.append(line)
            short = False
            continue
        if short and line.startswith(u"- "):
            keep.append(line[:240])
    return u"\n".join(keep)


def cmd_gaps(model, per_group=55, workers=3):
    text = io.open(DRAFT, encoding="utf-8").read()
    cited = set(int(x) for x in re.findall(r"#(\d+)", text))
    msgs = load_msgs()
    pool = []
    for i in sorted(msgs):
        if i in cited:
            continue
        r = msgs[i]
        t = (r.get("text") or u"").strip()
        if len(t) < 45 or len(t) > 600:
            continue
        if t.endswith(u"?") and len(t) < 200:
            continue
        if not ALCO.search(t):
            continue
        pool.append(r)
    a("pool (not cited): %d" % len(pool))

    def thin(rows, cap):
        if len(rows) <= cap:
            return rows
        step = len(rows) / float(cap)
        return [rows[int(i * step)] for i in range(cap)]

    groups = []
    rest = list(pool)
    rest_ids = set(r["id"] for r in rest)
    for name, rx in GROUPS:
        sel = [r for r in rest if rx.search(r.get("text") or u"")]
        groups.append((name, thin(sel, per_group)))
        sid = set(r["id"] for r in sel)
        rest = [r for r in rest if r["id"] not in sid]
    groups.append((u"ПРОЧЕЕ", thin(rest, per_group)))

    struct = outline(text)
    lock = threading.Lock()
    results = []

    def one(item):
        name, rows = item
        if not rows:
            return None
        prompt = GAPS_PROMPT % (struct, u"\n".join(msg_line(r, 500) for r in rows))
        t0 = time.time()
        try:
            txt = call(model, prompt)
            arr = last_json_array(txt)
            note = u"ok" if arr is not None else u"NO-JSON"
            arr = arr or []
        except Exception as exc:                       # noqa: BLE001
            arr, note = [], u"ERROR %s" % str(exc)[:120]
        with lock:
            results.append({"block": name, "ids": len(rows), "model": model,
                            "note": note, "findings": arr})
            a("gaps %-18s msgs=%3d %-6s %2d items %3.0fs"
              % (name.encode("ascii", "replace").decode("ascii"), len(rows),
                 note[:6], len(arr), time.time() - t0))
        return None

    with ThreadPoolExecutor(max_workers=workers) as pool_ex:
        list(pool_ex.map(one, groups))

    order = [n for n, _ in groups]
    results.sort(key=lambda r: order.index(r["block"]))
    with io.open(RAW, "a", encoding="utf-8", newline=u"\n") as f:
        for r in results:
            f.write(json.dumps(dict(r, pass_="gaps"), ensure_ascii=False) + u"\n")

    slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
    out_path = os.path.join(HERE, "_llm_alc_gaps_%s.txt" % slug)
    out = [u"model: %s" % model, u""]
    total = 0
    for r in results:
        if not r["findings"]:
            continue
        out.append(u"=== %s  [msgs=%d]" % (r["block"], r["ids"]))
        for f in r["findings"]:
            if not isinstance(f, dict):
                continue
            total += 1
            mid = f.get("id")
            try:
                mid = int(mid)
            except (TypeError, ValueError):
                mid = None
            src = msgs.get(mid)
            out.append(u"  #%s | %s" % (mid, f.get("fact", u"")))
            if src:
                out.append(u"      источник: %s" % msg_line(src, 260))
            else:
                out.append(u"      ВНИМАНИЕ: такого номера нет в экспорте")
            out.append(u"")
    bad = [r for r in results if r["note"] != u"ok"]
    out.insert(2, u"groups: %d, items: %d, failed: %d" % (len(results), total, len(bad)))
    io.open(out_path, "w", encoding="utf-8", newline=u"\n").write(u"\n".join(out))
    a("gaps: %d groups, %d items, %d failed -> %s"
      % (len(results), total, len(bad), os.path.basename(out_path)))
    return 0


BULLET_PROMPT = u"""Ты проверяешь одно утверждение путеводителя по Таджикистану.
Ниже утверждение и полные тексты сообщений чата, на которые оно ссылается.

Вопрос: следует ли утверждение из этих сообщений?

Проверь три вещи:
- нет ли в утверждении детали, которой в сообщениях нет (домысел);
- не приписано ли утверждение не тому сообщению (в сообщении о другом городе,
  бренде, заведении);
- нет ли обобщения, которого сообщения не дают (все, везде, никогда, единственный).

Ответ — строго JSON без текста вокруг:
{"supported": true или false, "issue": "до 120 символов или пустая строка"}
Если утверждение в порядке: {"supported": true, "issue": ""}.
Если в утверждении есть ссылка на чужие источники [->28] и нет ссылок на чат —
считай supported=true.

УТВЕРЖДЕНИЕ:
%s

СООБЩЕНИЯ:
%s
"""


def sentences(body):
    """Строки черновика -> отдельные утверждения с номерами сообщений."""
    out = []
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith((u"#", u"|", u"---")):
            continue
        s = re.sub(r"^[-*]\s+", u"", s)
        for part in re.split(r"(?<=[.!?])\s+(?=[А-ЯЁA-Z«\"(0-9])", s):
            p = part.strip()
            if len(p) < 25 or not re.search(r"#\d+", p):
                continue
            if re.search(r"\[→\d+\]", p) and not re.search(r"#\d+", p):
                continue
            out.append(p)
    return out


def last_json_object(txt):
    """Последний сбалансированный JSON-объект из ответа модели."""
    t = re.sub(r"^```[a-zA-Z]*|```$", u"", txt.strip()).strip()
    depth = 0
    start = None
    best = None
    for i, ch in enumerate(t):
        if ch == u"{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == u"}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    parsed = json.loads(t[start:i + 1])
                except ValueError:
                    continue
                if isinstance(parsed, dict):
                    best = parsed
    return best


class Pool(object):
    """Пул моделей с учётом квот: 429 отправляет модель в кулдаун."""

    def __init__(self, models, interval=2.0):
        self.models = list(models)
        self.interval = interval
        self.until = dict((m, 0.0) for m in models)
        self.fails = dict((m, 0) for m in models)
        self.lock = threading.Lock()

    def pick(self):
        while True:
            with self.lock:
                now = time.time()
                ready = [m for m in self.models if self.until[m] <= now]
                if ready:
                    m = min(ready, key=lambda x: (self.fails[x], self.until[x]))
                    self.until[m] = now + self.interval
                    return m
                wait = min(self.until.values()) - now
            time.sleep(max(0.5, min(wait, 5)))

    def fail(self, model, cooldown):
        with self.lock:
            self.fails[model] += 1
            self.until[model] = time.time() + cooldown


def prior_claims(model):
    """Уже разобранные утверждения: перезапуск не тратит квоту заново."""
    done = {}
    if not os.path.exists(RAW):
        return done
    with io.open(RAW, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("pass_") == "bullets" and r.get("supported") is not None:
                done[r.get("claim")] = r
    return done


def cmd_bullets(models, workers=1, cooldown=120):
    text = io.open(DRAFT, encoding="utf-8").read()
    msgs = load_msgs()
    done = prior_claims(models)
    jobs = []
    for head, body in chunks(text, maxlen=10 ** 9):
        for sent in sentences(body):
            ids = [int(x) for x in re.findall(r"#(\d+)", sent)]
            ids = [i for i in dict.fromkeys(ids) if i in msgs]
            if ids:
                jobs.append((head, sent, ids))
    todo = [j for j in jobs if j[1] not in done]
    a("claims: %d, todo: %d, already: %d" % (len(jobs), len(todo), len(jobs) - len(todo)))

    pool = Pool(models)
    results = []
    for n, job in enumerate(todo, 1):
        head, sent, ids = job
        prompt = BULLET_PROMPT % (sent, u"\n".join(msg_line(msgs[i], 900) for i in ids))
        obj = None
        for attempt in range(3):
            model = pool.pick()
            try:
                obj = last_json_object(call(model, prompt, max_tokens=600, tries=1))
                if obj is not None:
                    break
                pool.fail(model, 20)
            except Exception as exc:                  # noqa: BLE001
                msg = str(exc)
                pool.fail(model, cooldown if u"429" in msg else 20)
        if obj is None:
            obj = {"supported": None, "issue": u"no answer"}
        results.append({"pass_": "bullets", "block": head, "claim": sent, "ids": ids,
                        "supported": obj.get("supported"),
                        "issue": obj.get("issue") or u"", "model": model})
        with io.open(RAW, "a", encoding="utf-8", newline=u"\n") as f:
            f.write(json.dumps(results[-1], ensure_ascii=False, sort_keys=True) + u"\n")
        if obj.get("supported") is not True:
            a("  %3d/%d %-5s %s" % (n, len(todo), str(obj.get("supported"))[:5],
                                    sent[:58].encode("ascii", "replace").decode("ascii")))
        elif n % 20 == 0:
            a("  %3d/%d ok" % (n, len(todo)))

    allrows = dict(done)
    for r in results:
        allrows[r["claim"]] = r
    rows = [allrows.get(s) for _, s, _ in jobs if allrows.get(s)]
    slug = re.sub(r"[^a-z0-9]+", "-", u"+".join(models))[:60].strip("-")
    out_path = os.path.join(HERE, "_llm_alc_bullets_%s.txt" % slug)
    bad = [r for r in rows if r["supported"] is not True]
    out = [u"models: %s" % u", ".join(models),
           u"claims: %d, supported: %d, flagged: %d"
           % (len(rows), len(rows) - len(bad), len(bad)), u""]
    for r in bad:
        out.append(u"=== %s" % r["block"])
        out.append(u"  УТВЕРЖДЕНИЕ: %s" % r["claim"])
        out.append(u"  МОДЕЛЬ: %s | %s | %s" % (r.get("model"), r["supported"], r["issue"]))
        for i in r["ids"]:
            out.append(u"    %s" % msg_line(msgs[i], 400))
        out.append(u"")
    io.open(out_path, "w", encoding="utf-8", newline=u"\n").write(u"\n".join(out))
    a("bullets: %d claims, %d flagged -> %s"
      % (len(rows), len(bad), os.path.basename(out_path)))
    return 0


BATCH_PROMPT = u"""Ты проверяешь утверждения путеводителя по Таджикистану. Ниже несколько
утверждений; под каждым — тексты сообщений чата, на которые оно ссылается
(номер в утверждении = номер сообщения).

Для каждого утверждения ответь, следует ли оно из своих сообщений:
- нет ли детали, которой в сообщениях нет (домысел);
- не приписано ли утверждение не тому сообщению (в сообщении о другом городе,
  бренде, заведении);
- нет ли обобщения, которого сообщения не дают (все, везде, никогда, единственный).

Ответ — строго JSON-массив без текста вокруг, по одному объекту на утверждение:
[{"n": 1, "supported": true, "issue": ""}, {"n": 2, "supported": false, "issue": "до 100 символов"}]
issue для supported=true — пустая строка.

%s
"""


def cmd_batch(models, per=3, cooldown=90):
    text = io.open(DRAFT, encoding="utf-8").read()
    msgs = load_msgs()
    done = prior_claims(models)
    jobs = []
    for head, body in chunks(text, maxlen=10 ** 9):
        for sent in sentences(body):
            ids = [int(x) for x in re.findall(r"#(\d+)", sent)]
            ids = [i for i in dict.fromkeys(ids) if i in msgs]
            if ids:
                jobs.append((head, sent, ids))
    todo = [j for j in jobs if j[1] not in done]
    a("claims: %d, todo: %d, already: %d" % (len(jobs), len(todo), len(jobs) - len(todo)))

    pool = Pool(models, interval=1.0)
    results = []
    n_done = 0
    while todo:
        batch, todo = todo[:per], todo[per:]
        parts = []
        for k, (head, sent, ids) in enumerate(batch, 1):
            parts.append(u"%d) %s\nСООБЩЕНИЯ:\n%s"
                         % (k, sent, u"\n".join(msg_line(msgs[i], 800) for i in ids)))
        prompt = BATCH_PROMPT % u"\n\n".join(parts)
        arr = None
        for attempt in range(4):
            model = pool.pick()
            try:
                arr = last_json_array(call(model, prompt, max_tokens=1200, tries=1))
                if arr is not None:
                    break
                pool.fail(model, 20)
            except Exception as exc:                  # noqa: BLE001
                msg = str(exc)
                pool.fail(model, cooldown if u"429" in msg else 20)
        verdicts = {}
        for it in (arr or []):
            if isinstance(it, dict) and isinstance(it.get("n"), int):
                verdicts[it["n"]] = it
        for k, (head, sent, ids) in enumerate(batch, 1):
            v = verdicts.get(k) or {"supported": None, "issue": u"no answer"}
            rec = {"pass_": "bullets", "block": head, "claim": sent, "ids": ids,
                   "supported": v.get("supported"), "issue": v.get("issue") or u"",
                   "model": model}
            results.append(rec)
            with io.open(RAW, "a", encoding="utf-8", newline=u"\n") as f:
                f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + u"\n")
        n_done += len(batch)
        a("  %3d/%d batch=%d verdicts=%d" % (n_done, n_done + len(todo), len(batch),
                                             len(verdicts)))

    allrows = dict(done)
    for r in results:
        allrows[r["claim"]] = r
    rows = [allrows.get(s) for _, s, _ in jobs if allrows.get(s)]
    slug = re.sub(r"[^a-z0-9]+", "-", u"+".join(m.split("-")[0] for m in models))[:40]
    out_path = os.path.join(HERE, "_llm_alc_bullets_%s.txt" % slug)
    bad = [r for r in rows if r["supported"] is not True]
    out = [u"models: %s" % u", ".join(models),
           u"claims: %d, supported: %d, flagged: %d"
           % (len(rows), len(rows) - len(bad), len(bad)), u""]
    for r in bad:
        out.append(u"=== %s" % r["block"])
        out.append(u"  УТВЕРЖДЕНИЕ: %s" % r["claim"])
        out.append(u"  МОДЕЛЬ: %s | %s | %s" % (r.get("model"), r["supported"], r["issue"]))
        for i in r["ids"]:
            out.append(u"    %s" % msg_line(msgs[i], 400))
        out.append(u"")
    io.open(out_path, "w", encoding="utf-8", newline=u"\n").write(u"\n".join(out))
    a("bullets: %d claims, %d flagged -> %s"
      % (len(rows), len(bad), os.path.basename(out_path)))
    return 0


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("facts", "gaps", "bullets", "batch"):
        a("usage: _llm_review_62.py facts|gaps|bullets|batch <model[,model]> [workers]")
        return 2
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    t0 = time.time()
    cmd = sys.argv[1]
    models = [m.strip() for m in sys.argv[2].split(",") if m.strip()]
    if cmd == "facts":
        rc = cmd_facts(models[0], workers)
    elif cmd == "gaps":
        rc = cmd_gaps(models[0], workers=workers)
    elif cmd == "batch":
        rc = cmd_batch(models)
    else:
        rc = cmd_bullets(models, workers=workers)
    a("done in %.0fs" % (time.time() - t0))
    return rc


if __name__ == "__main__":
    sys.exit(main())
