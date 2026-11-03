# -*- coding: utf-8 -*-
"""_cluster_llm.py — кластеризация выгрузки чата в поисках новых разделов.

Разделы, которые уже собраны в путеводителе, задаём списком (EXISTING) и
передаём модели: она помечает каждое сообщение либо номером существующего
раздела, либо 0 — «под существующие рамки не подпадает».

Режимы:
  sample            — стратифицированная выборка сообщений, задающих тему
  label  <models>   — LLM: метка темы + покрытие для каждого сообщения выборки
  merge  <models>   — LLM: схлопнуть словарь меток в канонические темы
  size              — детерминистический подсчёт каждой темы по всему корпусу
  rank   <models>   — LLM: предложить список кандидатов-разделов по готовой
                      таблице тем
  report            — собрать md-файл с кандидатами

Запуск: python _cluster_llm.py sample
        python _cluster_llm.py label gemini-3.5-flash-lite,gemini-3-flash-preview
"""
import io
import json
import os
import random
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

import _llm_review_62 as R

HERE = os.path.dirname(os.path.abspath(__file__))
MSGS = os.path.join(HERE, "messages.jsonl")
POOL = os.path.join(HERE, "_topics_pool.jsonl")
SAMPLE = os.path.join(HERE, "_topics_sample.jsonl")
LABELS = os.path.join(HERE, "_topics_labels.jsonl")
MERGED = os.path.join(HERE, "_topics_merged.json")
SIZES = os.path.join(HERE, "_topics_sizes.json")
RANKS = os.path.join(HERE, "_topics_rank.jsonl")
LOCK = threading.Lock()
# минимальный вес кластера, чтобы под него подбирать корни и размерять
MIN_LABELS = 3

# существующие части путеводителя: модель должна отнести сообщение сюда или в 0
EXISTING = [
    (1, u"Виза и регистрация",
     u"виза, сроки пребывания, регистрация, миграционная карта, пермит ГБАО, "
     u"погранзона, штрафы за просрочку, границы"),
    (2, u"Жильё",
     u"аренда долгосрочная и посуточная, бронирование, гостиницы, хостелы, "
     u"санатории, турбазы, альплагеря, цены на жильё, ночёвка в кишлаке"),
    (3, u"Деньги и банки",
     u"карты (Мир, Visa, MC), банкоматы, обмен валют, наличные, переводы, "
     u"кошельки, банки и их отделения, цены на товары и услуги"),
    (4, u"Транспорт",
     u"самолёты, поезд, автобусы, маршрутки, таксо, городской транспорт, "
     u"дороги, перевалы, тоннели, аренда авто, маршрут по стране"),
    (5, u"Связь и интернет",
     u"сим-карты, операторы, тарифы, мобильный интернет, Wi-Fi, роуминг, "
     u"салоны связи, мессенджеры как способ связи"),
    (6, u"Места",
     u"города, достопримечательности, что посмотреть, маршруты по местам, "
     u"озёра, горы, водопады, руины, парки, архитектура"),
    (7, u"Еда и заведения",
     u"что есть, чайханы, кафе, рестораны, кофейни, доставка, фудкорты, "
     u"гигиена за столом, блюда и продукты, заведения по городам"),
    (8, u"Алкоголь и табак",
     u"пиво, пивзаводы, вино, водка, коньяк, крафт, бары, пабы, пивные, "
     u"алкогольные магазины, дьюти-фри, ввоз и вывоз алкоголя, табак и кальян"),
    (9, u"Покупки",
     u"базары, рынки, магазины, ТЦ, ремёсла, сувениры, что дорого/дёшево, "
     u"торг, техника и пауэрбанки, карточки магазинов и категорий"),
    (10, u"Прочее бытовое",
     u"язык, этикет, отношение к туристам, безопасность, электричество, вода, "
     u"быт, сезон и погода, когда ехать, традиции, фото-съёмка"),
    (11, u"Залы и спорт",
     u"тренажёрные залы, фитнес, спорт, бег, йога"),
    (12, u"Медицина",
     u"врачи, клиники, аптеки, анализы, страховка, горная болезнь, лекарства, "
     u"травмы, зубной, прививки"),
    (13, u"Секс-шопы",
     u"секс-товары, контрацепция, интимные товары"),
    (14, u"Знакомства",
     u"знакомства, приложения для знакомств, куда сходить с девушкой, "
     u"свадьба, брак, отношения"),
]

EXISTING_TXT = u"\n".join(
    u"%d. %s — %s" % (n, t, d) for n, t, d in EXISTING)

LABEL_PROMPT = u"""Ты размечаешь форумный чат путешественников по Таджикистану.

Существующие разделы путеводителя:
%s

Ниже %%d сообщений чата. Для каждого укажи:
  n — номер сообщения;
  c — номер раздела из списка выше, куда по-человечески попадает вопрос,
      или 0, если ни в один не попадает (тогда тема должна быть своей);
  t — короткая метка темы в 1-4 слова, именительный падеж, со строчной буквы
      (например: «виза на въезде», «стиральная машина», «рыбалка»).
Метка для c=0 должна называть ЧАСТНУЮ тему, а не «разное» и не «вопрос».

Отвечай только JSON-массивом вида
[{"n": 1, "c": 4, "t": "аренда авто"}, ...] без пояснений.

Сообщения:
""" % EXISTING_TXT


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with io.open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows):
    with io.open(path, "w", encoding="utf-8", newline=u"\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + u"\n")


def kept_ids():
    """пул без шаблонных рассылок: по нему сверяем уже готовые метки"""
    return set(r["id"] for r in load_jsonl(POOL))


def norm_topic(s):
    s = (s or u"").strip().lower().rstrip(u".;,!")
    s = re.sub(u"[\\u0401\\u0451]", u"ё", s)
    s = re.sub(u"\\s+", u" ", s)
    return s[:60]


def stem(topic):
    """грубый стем: первые 5 букв каждого слова — для склейки синонимов"""
    return u" ".join(w[:5] for w in norm_topic(topic).split() if w)


# служебные сообщения самого чата: правила, модерация, приветствия-благодарности
CHATMETA = re.compile(
    u"(?i)(правила (чата|форума|группы)|модератор|забан|бан за|тг.?каталог|"
    u"каталог телеграм|телеграм-каталог|подписчик|реклама канал|бот в чате|"
    u"чат переполнен|здесь обсужда|этом чате можно|сообщество travelask|"
    u"спасибо всем|благодарю за ответы|с днём рождения|поздравля|"
    u"всем хорошей дороги|хорошего дня всем|кому интерес|присоединяюсь к вопросу)")

# темы-пустышки, которые модель выдаёт вместо содержательной метки
JUNK_TOPICS = set([
    u"приветствие", u"благодарность", u"оффтоп", u"разное", u"вопрос",
    u"уточнение", u"неясно", u"общение", u"флуд", u"болтовня", u"прочее",
    u"не знаю", u"беседка", u"комплимент", u"заявка", u"ожидание ответа",
])


# ---------------------------------------------------------------- sample
def cmd_sample(per_month=45, seed=20261103):
    rows = load_jsonl(POOL)
    rows = [r for r in rows if not CHATMETA.search(r["text"])]
    by_month = defaultdict(list)
    for r in rows:
        d = r.get("date") or u""
        m = re.match(u"(\\d{2})\\.(\\d{2})\\.(\\d{4})", d)
        key = m.group(2) + m.group(3) if m else u"??"
        by_month[key].append(r)
    rnd = random.Random(seed)
    picked = []
    for key in sorted(by_month):
        bucket = by_month[key][:]
        rnd.shuffle(bucket)
        picked.extend(bucket[:per_month])
    picked.sort(key=lambda r: r["id"])
    write_jsonl(SAMPLE, picked)
    print("pool=%d months=%d sample=%d" % (len(rows), len(by_month), len(picked)))
    return 0


# ---------------------------------------------------------------- label
def label_batch(model, batch, base):
    lines = []
    for i, r in enumerate(batch):
        txt = re.sub(u"\\s+", u" ", r["text"])[:200]
        lines.append(u"%d) %s" % (base + i, txt))
    prompt = (LABEL_PROMPT % len(batch)) + u"\n".join(lines)
    try:
        out = R.call(model, prompt, max_tokens=3200)
    except Exception:
        out = None
    return R.last_json_array(out) if out else None


def cmd_label(models, per=30, workers=4, cooldown=120, limit=None):
    keep = kept_ids()
    rows = [r for r in load_jsonl(SAMPLE)
            if r["id"] in keep and not CHATMETA.search(r["text"])]
    done = set(r["id"] for r in load_jsonl(LABELS))
    todo = [r for r in rows if r["id"] not in done]
    if limit:
        todo = todo[:limit]
    if not todo:
        print("nothing to label: %d of %d done" % (len(done), len(rows)))
        return 0
    pool = R.Pool(models, interval=6.0)
    batches = [todo[i:i + per] for i in range(0, len(todo), per)]
    got = [0, 0]

    def work(bi):
        batch = batches[bi]
        m = pool.pick()
        arr = label_batch(m, batch, 1)
        if not arr:
            pool.fail(m, cooldown)
            m = pool.pick()
            arr = label_batch(m, batch, 1)
        if not arr:
            with LOCK:
                got[1] += 1
            return 0
        recs = []
        by_n = {}
        for it in (arr or []):
            if isinstance(it, dict) and isinstance(it.get("n"), int):
                by_n[it["n"]] = it
        for i, r in enumerate(batch):
            it = by_n.get(i + 1)
            if it is None:
                recs.append({"id": r["id"], "date": r["date"], "c": None,
                             "t": None, "model": m, "miss": 1})
            else:
                recs.append({"id": r["id"], "date": r["date"],
                             "c": it.get("c"), "t": norm_topic(it.get("t")),
                             "model": m, "miss": 0})
        with LOCK:
            got[0] += 1
            with io.open(LABELS, "a", encoding="utf-8") as f:
                for rec in recs:
                    f.write(json.dumps(rec, ensure_ascii=False) + u"\n")
            if got[0] % 5 == 0:
                print("labeled %d/%d batches, failed %d" %
                      (got[0], len(batches), got[1]), flush=True)
        return len(recs)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, range(len(batches))))
    print("labeled total: %d, batches failed this run: %d" %
          (len(load_jsonl(LABELS)), got[1]))
    return 0


MERGE_PROMPT = u"""Ниже словарь тем, которые встретились в чате про Таджикистан
и НЕ попали ни в один из готовых разделов путеводителя. Формат: тема | сколько раз.

Схлопни эти темы в канонические кластеры: не больше 45, только те, куда попадает
хотя бы две темы. Каждую исходную тему из списка отнеси ровно в один кластер
(синонимы, варианты падежа, частные случаи одного предмета — вместе). Мусор
(обрывок, «вопрос», «приветствие», «реклама») в кластер "мусор". Темы, которые
никуда не подходят, не выдумывай: их просто не будет в ответе.

Отвечай только JSON:
[{"name": "название кластера (2-5 слов, им. падеж)",
  "members": ["тема1", "тема2", ...]}, ...]

Словарь:
"""


def vocab_all():
    """словарь непокрытых тем: метки разметки (вес 1) + свободный sweep (вес n)"""
    cnt = Counter()
    for r in load_jsonl(LABELS):
        if r.get("c") != 0 or not r.get("t"):
            continue
        t = norm_topic(r["t"])
        if t and t not in JUNK_TOPICS and not is_trash(t):
            cnt[t] += 1
    if os.path.exists(FREE):
        for rec in load_jsonl(FREE):
            t = norm_topic(rec.get("t"))
            if not t or t in JUNK_TOPICS or is_trash(t):
                continue
            try:
                n = int(rec.get("n") or 1)
            except (TypeError, ValueError):
                n = 1
            cnt[t] += max(1, n)
    return cnt


def cmd_merge(models, min_count=2, maxlen=11000):
    cnt = vocab_all()
    head = [(t, c) for t, c in cnt.most_common() if c >= min_count]
    batches = []
    cur, size = [], 0
    for tv in head:
        add = len(tv[0]) + 8
        if size + add > maxlen and cur:
            batches.append(cur)
            cur, size = [], 0
        cur.append(tv)
        size += add
    if cur:
        batches.append(cur)
    prev = []
    if os.path.exists(MERGED):
        prev = json.load(io.open(MERGED, encoding="utf-8")).get("clusters", [])
    done = set(c.get("b", -1) for c in prev if c.get("members"))
    clusters = [c for c in prev if c.get("members")]
    pool = R.Pool(models, interval=5.0)
    for bi, batch in enumerate(batches):
        if bi in done:
            print("merge batch %d: already merged" % bi, flush=True)
            continue
        body = u"\n".join(u"%s | %d" % tv for tv in batch)
        arr = None
        for _try in range(3):
            m = pool.pick()
            try:
                out = R.call(m, MERGE_PROMPT + body, max_tokens=6000, tries=1)
            except Exception:
                out = None
            arr = R.last_json_array(out) if out else None
            if arr is None:
                pool.fail(m, cooldown=120)
            else:
                break
        if not arr:
            print("batch %d: no json, retry later" % bi, flush=True)
            continue
        given = set()
        for cl in arr:
            if not isinstance(cl, dict):
                continue
            name = norm_topic(cl.get("name"))
            mem = [norm_topic(x) for x in (cl.get("members") or [])]
            mem = [x for x in mem if x]
            if not name or len(mem) < 2:
                continue
            clusters.append({"name": name, "members": mem, "b": bi})
            given.update(mem)
        lost = sorted(set(t for t, _ in batch) - given)
        json.dump({"clusters": clusters},
                  io.open(MERGED, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("merge batch %d: +%d clusters, %d unmatched" %
              (bi, len(arr), len(lost)), flush=True)
        for t in lost[:6]:
            print("   lost: %s" % t.encode("ascii", "replace").decode("ascii"),
                  flush=True)
    json.dump({"clusters": clusters}, io.open(MERGED, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("clusters: %d, head topics: %d, batches: %d" %
          (len(clusters), len(head), len(batches)))
    return 0


# ------------------------------------------------------------------ expand
EXPAND_PROMPT = u"""Кластер тем из чата путешественников по Таджикистану.
Название: %s
Темы внутри кластера: %s

Выдай 6-14 корней слов, по которым в обычных сообщениях этого чата можно найти
сообщения той же темы. Корень — 5-8 букв, строчными буквами, без пробелов, это
начало слова без окончания. Не включай общие слова («подскажите», «таджикистан»,
«город», «вопрос») и сами названия кластеров. Отвечай только JSON-массивом
строк: ["пвз", "пропуск", ...]
"""

GENERIC = set([
    u"таджик", u"душанб", u"худжанд", u"подскаж", u"посовет", u"знает",
    u"ребят", u"здравств", u"пожалу", u"спасиб", u"пожалу", u"вопрос",
    u"сообщ", u"интерес", u"очень", u"хочет", u"хочу", u"можно", u"нужно",
    u"какие", u"какой", u"где", u"когда", u"как", u"что", u"есть", u"был",
])


def cmd_expand(models, workers=4, cooldown=120, min_weight=MIN_LABELS):
    cl = [c for c in clusters_from_labels() if not is_trash(c["name"])]
    todo = [c for c in cl if c["weight"] >= min_weight and "stems" not in c]
    if not todo:
        print("stems ready for %d clusters" % len(cl))
        return 0
    pool = R.Pool(models, interval=6.0)
    done = [0]

    def work(c):
        m = pool.pick()
        names = u", ".join(t for t, _ in c["topics"][:14])
        prompt = EXPAND_PROMPT % (c["name"], names)
        try:
            out = R.call(m, prompt, max_tokens=700)
        except Exception:
            out = None
        arr = R.last_json_array(out) if out else None
        if not arr:
            pool.fail(m, cooldown)
            return 0
        stems = []
        for s in arr:
            s = re.sub(u"[^a-zа-яё]", u"", norm_topic(s if isinstance(s, str)
                                                        else u""))
            if len(s) >= 5 and s not in GENERIC and s not in stems:
                stems.append(s)
        if not stems:
            return 0
        with LOCK:
            done[0] += 1
            save_clusters(c["name"], {"stems": stems[:14]})
            if done[0] % 5 == 0:
                print("expanded %d/%d" % (done[0], len(todo)), flush=True)
        return len(stems)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, todo))
    print("expanded: %d of %d" % (done[0], len(todo)))
    return 0


STEMS = os.path.join(HERE, "_topics_stems.json")
# кластеры, которые модель собрала в мусор, не размеряем и не расширяем
TRASH = (u"мусор", u"служебн", u"приветств", u"благодарн", u"реклама",
         u"модерац", u"оффтоп", u"флуд")


def is_trash(name):
    n = norm_topic(name)
    return any(x in n for x in TRASH)



def load_stems():
    if os.path.exists(STEMS):
        return json.load(io.open(STEMS, encoding="utf-8"))
    return {}


def save_clusters(name, patch):
    st = load_stems()
    st[name] = dict(st.get(name, {}))
    st[name].update(patch)
    json.dump(st, io.open(STEMS, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


def free_weights():
    fw = Counter()
    if not os.path.exists(FREE):
        return fw
    for rec in load_jsonl(FREE):
        t = norm_topic(rec.get("t"))
        if not t or t in JUNK_TOPICS or is_trash(t):
            continue
        try:
            n = int(rec.get("n") or 1)
        except (TypeError, ValueError):
            n = 1
        fw[t] += max(1, n)
    return fw


def clusters_from_labels():
    """словарь непокрытых тем -> кластеры; имя = каноническое имя из merge"""
    keep = kept_ids()
    fw = free_weights()
    nlab = Counter()
    ids_by_topic = {}
    for r in load_jsonl(LABELS):
        if r.get("c") != 0 or not r.get("t") or r["id"] not in keep:
            continue
        t = norm_topic(r["t"])
        if not t or t in JUNK_TOPICS or is_trash(t):
            continue
        nlab[t] += 1
        ids_by_topic.setdefault(t, []).append(r["id"])
    member2cl = {}
    order = []
    if os.path.exists(MERGED):
        for cl in json.load(io.open(MERGED, encoding="utf-8"))["clusters"]:
            name = norm_topic(cl.get("name"))
            if not name:
                continue
            if name not in member2cl.values():
                order.append(name)
            for mem in cl.get("members", []):
                member2cl.setdefault(norm_topic(mem), name)
    vc = vocab_all()
    agg = {}
    for t in vc:
        name = member2cl.get(t, t)
        if not name or is_trash(name):
            continue
        if name not in agg:
            agg[name] = {"name": name, "topics": Counter(), "ids": []}
        agg[name]["topics"][t] = vc[t]
        agg[name]["ids"] += ids_by_topic.get(t, [])
    st = load_stems()
    out = []
    for name, a in agg.items():
        a["nlab"] = len(a["ids"])
        a["nfree"] = sum(fw.get(t, 0) for t in a["topics"])
        a["weight"] = a["nlab"] + a["nfree"]
        a["topics"] = a["topics"].most_common()
        if name in st:
            a["stems"] = st[name].get("stems")
        out.append(a)
    out.sort(key=lambda x: -x["weight"])
    return out


# -------------------------------------------------------------------- size
CORPUS = None


def norm_text(s):
    s = (s or u"").lower().replace(u"ё", u"е")
    s = re.sub(u"[^a-zа-я0-9]+", u" ", s)
    return re.sub(u"\\s+", u" ", s).strip()


def load_corpus():
    global CORPUS
    if CORPUS is not None:
        return CORPUS
    rows = load_jsonl(MSGS)
    pool_ids = set(r["id"] for r in load_jsonl(POOL))
    CORPUS = ([(r["id"], year_of(r.get("date")), norm_text(r.get("text")),
               r["id"] in pool_ids, r.get("author") or u"") for r in rows],
              pool_ids)
    return CORPUS


def year_of(date):
    m = re.search(u"(\\d{4})", date or u"")
    return m.group(1) if m else u"??"


def cmd_size(min_labels=MIN_LABELS):
    corpus, _ = load_corpus()
    cl = clusters_from_labels()
    sized = []
    for c in cl:
        stems = c.get("stems") or []
        stems = [re.sub(u"[^a-zа-я]", u"", s)[:8] for s in stems]
        stems = [s for s in stems if len(s) >= 5 and s not in GENERIC]
        if not stems:
            continue
        rx1 = re.compile(u"\\b(?:" + u"|".join(map(re.escape, stems)) + u")")
        rxs = [re.compile(u"\\b" + re.escape(s)) for s in stems]
        hits = 0
        strong = 0
        qhits = 0
        authors = set()
        years = Counter()
        examples = []
        for mid, year, txt, isq, author in corpus:
            if not txt or not rx1.search(txt):
                continue
            hits += 1
            n = sum(1 for rx in rxs if rx.search(txt))
            if n >= 2:
                strong += 1
                if isq:
                    qhits += 1
                authors.add(author)
                years[year] += 1
                if len(txt) > 60 and len(examples) < 40:
                    examples.append((mid, year, n, len(txt)))
        sized.append({"name": c["name"], "stems": stems, "nlab": c["nlab"],
                      "topics": c["topics"][:8], "hits": hits, "strong": strong,
                      "qhits": qhits, "authors": len(authors),
                      "years": dict(years),
                      "examples": [e[0] for e in examples[:12]]})
    sized.sort(key=lambda x: -x["strong"])
    json.dump(sized, io.open(SIZES, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("sized clusters: %d (>=100 strong: %d)" %
          (len(sized), sum(1 for s in sized if s["strong"] >= 100)))
    return 0


# -------------------------------------------------------------------- rank
RANK_PROMPT = u"""Ты редактор путеводителя по Таджикистану.

Уже есть такие разделы:
%s

Ниже — кластеры тем из чата, которые в эти разделы не попали, с размерами,
посчитанными по всему корпусу сообщений (strong — сообщения, где встретилось не
менее двух корней темы; qhits — из них вопросы, задающие тему).

%s

Предложи 8-18 кандидатов в НОВЫЕ разделы путеводителя. Каждый кандидат должен
опираться на кластеры выше (можно склеить несколько близких кластеров в один
раздел, можно отбросить кластер, если он слишком мелкий). Для каждого верни:
  name — название раздела (2-5 слов);
  includes — какие кластеры из таблицы входят (их названия);
  scope — что именно будет в разделе, 1-2 предложения;
  why — почему это отдельный раздел, а не подраздел существующего;
  closer — номер существующего раздела, к которому это ближе всего, или 0;
  priority — 1 (обязательно) … 5 (можно не делать);
  risk — чем плох этот раздел (мало данных, дублирует, одноразовые вопросы).
Отвечай только JSON-массивом объектов. Никаких пояснений вне JSON.
"""


def cmd_rank(models, min_strong=30, top=90):
    sized = json.load(io.open(SIZES, encoding="utf-8"))
    cand = [s for s in sized if s["strong"] >= min_strong][:top]
    lines = []
    for s in cand:
        lines.append(u"%s | strong=%d | hits=%d | qhits=%d | авт.%d | %s" % (
            s["name"], s["strong"], s["hits"], s["qhits"], s["authors"],
            u", ".join(t for t, _ in s["topics"][:6])))
    table = u"\n".join(lines)
    prompt = RANK_PROMPT % (EXISTING_TXT, table)
    pool = R.Pool(models, interval=8.0)
    res = []
    for m in models:
        try:
            out = R.call(m, prompt, max_tokens=9000, tries=1)
        except Exception:
            out = None
        arr = R.last_json_array(out) if out else None
        if not arr:
            print("rank %s: no json" % m, flush=True)
            continue
        for it in arr:
            if isinstance(it, dict) and it.get("name"):
                it["model"] = m
                res.append(it)
        with io.open(RANKS, "a", encoding="utf-8") as f:
            for it in res[-len(arr):]:
                f.write(json.dumps(it, ensure_ascii=False) + u"\n")
        print("rank %s: %d candidates" % (m, len(arr)), flush=True)
    print("rank total: %d" % len(res))
    return 0


CANDSIZES = os.path.join(HERE, "_cand_sizes.json")


def clean_stems(stems):
    out = []
    for s in stems or []:
        s = re.sub(u"[^a-zа-яё]", u"", norm_topic(s))[:8]
        if len(s) >= 5 and s not in GENERIC and s not in out:
            out.append(s)
    return out


def measure(stems, corpus, want=14):
    """Объединённый замер по корням: сколько сообщений, какие id примеров."""
    stems = clean_stems(stems)
    if not stems:
        return None
    rx1 = re.compile(u"\\b(?:" + u"|".join(map(re.escape, stems)) + u")")
    rxs = [re.compile(u"\\b" + re.escape(s)) for s in stems]
    hits = strong = qhits = 0
    authors = set()
    years = Counter()
    ex_q, ex_a = [], []
    for mid, year, txt, isq, author in corpus:
        if not txt or not rx1.search(txt):
            continue
        hits += 1
        n = sum(1 for rx in rxs if rx.search(txt))
        if n < 2:
            continue
        strong += 1
        authors.add(author)
        years[year] += 1
        if isq:
            qhits += 1
            if len(ex_q) < want * 4:
                ex_q.append((mid, year, n, len(txt)))
        elif len(ex_a) < want:
            ex_a.append((mid, year, n, len(txt)))
    ex_q.sort(key=lambda e: (-e[2], -e[3]))
    return {"stems": stems, "hits": hits, "strong": strong, "qhits": qhits,
            "authors": len(authors), "years": dict(years),
            "ex_q": [e[0] for e in ex_q[:want]],
            "ex_a": [e[0] for e in ex_a[:max(0, want - 6)]]}


def match_includes(items, sized):
    """названия кластеров из уст модели -> настоящие кластеры таблицы"""
    idx = {}
    for s in sized:
        idx[s["name"]] = s
        for t, _ in s["topics"]:
            idx.setdefault(t, s)
    hit, miss = [], []
    for w in items or []:
        w = norm_topic(u"".join(ch for ch in (w or u"") if ch.isalpha() or ch.isspace()))
        if not w:
            continue
        if w in idx:
            hit.append(idx[w])
            continue
        ws = set(stem(w).split())
        best, bn = None, 0
        for k, v in idx.items():
            n = len(ws & set(stem(k).split()))
            if n > bn:
                bn, best = n, v
        (hit if bn >= 1 else miss).append(best if bn >= 1 else w)
    uniq, seen = [], set()
    for h in hit:
        if h["name"] not in seen:
            seen.add(h["name"])
            uniq.append(h)
    return uniq, miss


def cmd_measure(top=60):
    sized = json.load(io.open(SIZES, encoding="utf-8"))
    ranked = load_jsonl(RANKS)
    corpus, _ = load_corpus()
    texts = dict((r["id"], re.sub(u"\\s+", u" ", r["text"])) for r in
                 load_jsonl(MSGS))
    out = []
    for it in ranked:
        cl, miss = match_includes(it.get("includes"), sized)
        stems = []
        for c in cl:
            stems += clean_stems(c.get("stems"))
        m = measure(stems, corpus)
        if not m:
            continue
        m["name"] = norm_topic(it.get("name"))
        m["model"] = it.get("model")
        m["clusters"] = [c["name"] for c in cl]
        m["unmatched"] = miss
        m["scope"] = it.get("scope")
        m["why"] = it.get("why")
        m["closer"] = it.get("closer")
        m["priority"] = it.get("priority")
        m["risk"] = it.get("risk")
        m["quotes"] = [(i, texts.get(i, u"")[:400]) for i in
                        (m["ex_q"] + m["ex_a"])]
        out.append(m)
    out.sort(key=lambda x: -x["strong"])
    json.dump(out[:top], io.open(CANDSIZES, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("measured candidates: %d" % min(len(out), top))
    return 0


RESID = os.path.join(HERE, "_residual.jsonl")
FREE = os.path.join(HERE, "_topics_free.jsonl")

TOPICS_PROMPT = u"""Ты разбираешь чат путешественников по Таджикистану.

Разделы готового путеводителя:
%s

Ниже %%d сообщений. Нужно вытащить из них темы, которые НЕ покрываются ни одним
разделом выше: то, о чём в путеводителе пока негде прочитать.
Выпи ВСЕ такие темы, по которым есть хотя бы одно сообщение, максимум 12 тем на
пачку. Для каждой темы: название 2-4 слова, именительный падеж, со строчной
буквы, и n — сколько сообщений из пачки этой темы касаются. Служебное
(приветствия, благодарность, правила чата, «написать в личку», реклама) не
считай — таких тем не выдавай. Если всё покрыто разделами — верни пустой массив.

Отвечай только JSON-массивом: [{"t": "доставка посылок", "n": 3}, ...]

Сообщения:
""" % EXISTING_TXT


def cmd_topics(models, per=45, workers=4, cooldown=90, limit=None):
    rows = load_jsonl(RESID)
    rows = [r for r in rows if not CHATMETA.search(r["text"])]
    done_batches = set()
    if os.path.exists(FREE):
        for rec in load_jsonl(FREE):
            done_batches.add(rec.get("b"))
    batches = [(i, rows[i:i + per]) for i in range(0, len(rows), per)]
    todo = [bt for bt in batches if bt[0] not in done_batches]
    if limit:
        todo = todo[:limit]
    if not todo:
        print("nothing to do: %d batches" % len(batches))
        return 0
    pool = R.Pool(models, interval=3.0)
    got = [0, 0]

    def work(idx):
        bi, batch = todo[idx]
        m = pool.pick()
        lines = []
        for j, r in enumerate(batch):
            txt = re.sub(u"\\s+", u" ", r["text"])[:170]
            lines.append(u"%d) %s" % (j + 1, txt))
        prompt = (TOPICS_PROMPT % len(batch)) + u"\n".join(lines)
        try:
            out = R.call(m, prompt, max_tokens=2800, tries=2)
        except Exception:
            out = None
        arr = R.last_json_array(out) if out else None
        if arr is None:
            pool.fail(m, cooldown)
            with LOCK:
                got[1] += 1
            return 0
        recs = []
        for it in arr:
            if not isinstance(it, dict):
                continue
            t = norm_topic(it.get("t"))
            if not t or t in JUNK_TOPICS or is_trash(t):
                continue
            try:
                n = int(it.get("n") or 1)
            except (TypeError, ValueError):
                n = 1
            recs.append({"b": bi, "t": t, "n": max(1, min(n, len(batch))),
                         "model": m})
        if not recs:
            recs.append({"b": bi, "t": u"", "n": 0, "model": m})
        with LOCK:
            got[0] += 1
            with io.open(FREE, "a", encoding="utf-8") as f:
                for rec in recs:
                    f.write(json.dumps(rec, ensure_ascii=False) + u"\n")
            if got[0] % 10 == 0:
                print("topics %d/%d batches, no-answer %d" %
                      (got[0], len(todo), got[1]), flush=True)
        return len(recs)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, range(len(todo))))
    print("topics batches ok=%d fail=%d of %d; records=%d" %
          (got[0], got[1], len(todo), len(load_jsonl(FREE))))
    return 0


DRAFT = os.path.join(HERE, "_candidates_draft.txt")
GREET_START = re.compile(
    u"(?i)^(здравствуйте|привет|добрый день|доброе утро|дорогие|уважаемые|"
    u"ассаламу[^,]*|салями?|hello|hi)[\\s,.!-]+")


def snippet(text, limit=170):
    t = re.sub(u"\\s+", u" ", text or u"").strip()
    m = GREET_START.match(t)
    if m and len(t) - m.end() > 40:
        t = t[m.end():].strip()
    cut = t[:limit]
    if len(t) > limit:
        sp = cut.rfind(u" ")
        if sp > 40:
            cut = cut[:sp]
    cut = cut.rstrip(u" ,;:.!?-\u0451")
    return cut


def cmd_draft(top=40):
    """черновик с числами и цитатами: текст раздела пишет человек по этому каркасу"""
    sized = json.load(io.open(SIZES, encoding="utf-8"))
    cands = json.load(io.open(CANDSIZES, encoding="utf-8"))
    dates = {}
    texts = {}
    for r in load_jsonl(MSGS):
        dates[r["id"]] = (r.get("date") or u"")[:10]
        texts[r["id"]] = r.get("text") or u""
    lines = []
    for i, c in enumerate(cands[:top]):
        lines.append(u"## %s" % c["name"])
        lines.append(u"priority=%s closer=%s model=%s" %
                     (c.get("priority"), c.get("closer"), c.get("model")))
        lines.append(u"scope: %s" % c.get("scope"))
        lines.append(u"why: %s" % c.get("why"))
        lines.append(u"risk: %s" % c.get("risk"))
        lines.append(u"объём: hits=%d strong=%d qhits=%d авторов=%d годы=%s" % (
            c["hits"], c["strong"], c["qhits"], c["authors"],
            u",".join(u"%s:%d" % kv for kv in sorted(c["years"].items()))))
        lines.append(u"кластеры: %s" % u", ".join(c["clusters"][:10]))
        if c.get("unmatched"):
            lines.append(u"не сопоставлено: %s" % u", ".join(c["unmatched"][:6]))
        lines.append(u"корни: %s" % u", ".join(c["stems"][:14]))
        lines.append(u"примеры:")
        shown = 0
        for mid, _txt in c["quotes"]:
            s = snippet(_txt)
            if len(s) < 30 or u"http" in s.lower():
                continue
            lines.append(u"  \u00ab%s\u00bb (#%s, %s)" % (s, mid, dates.get(mid)))
            shown += 1
            if shown >= 6:
                break
        lines.append(u"")
    io.open(DRAFT, "w", encoding="utf-8", newline=u"\n").write(u"\n".join(lines))
    print("draft: %d candidates, %d lines" % (min(len(cands), top), len(lines)))
    return 0


def cmd_fallback_stems(min_weight=8):
    """Запасной ход, когда кончилась квота: корни из названий тем кластера."""
    cl = [c for c in clusters_from_labels()
          if c["weight"] >= min_weight and not c.get("stems")
          and not is_trash(c["name"])]
    done = 0
    for c in cl:
        roots = []
        for t, _n in c["topics"]:
            for wd in t.split():
                root = re.sub(u"[^a-zа-я]", u"", wd)[:7]
                if len(root) < 5 or root in GENERIC or root in roots:
                    continue
                roots.append(root)
        if not roots:
            continue
        save_clusters(c["name"], {"stems": roots[:12], "fallback": True})
        done += 1
    print("fallback stems for %d of %d clusters" % (done, len(cl)))
    return 0


def cmd_fvocab(min_w=1):
    """словарь свободного прохода: тема | вес | сколькими пачками найдена"""
    vc = Counter()
    bc = Counter()
    for rec in load_jsonl(FREE):
        t = norm_topic(rec.get("t"))
        if not t or t in JUNK_TOPICS or is_trash(t):
            continue
        try:
            n = int(rec.get("n") or 1)
        except (TypeError, ValueError):
            n = 1
        vc[t] += max(1, n)
        bc[t] += 1
    lines = []
    for t, w in vc.most_common():
        if w < min_w:
            continue
        lines.append(u"%s | %d | %d" % (t, w, bc[t]))
    io.open(os.path.join(HERE, "_topics_free_top.txt"), "w",
            encoding="utf-8", newline=u"\n").write(u"\n".join(lines))
    print("free vocab: %d topics, weight sum %d" % (len(vc), sum(vc.values())))
    return 0


FREFINED = os.path.join(HERE, "_cand_refined.json")
CFINAL = os.path.join(HERE, "_cand_final.jsonl")

CONSOLIDATE_PROMPT = u"""Ты главный редактор путеводителя по Таджикистану.

Уже есть такие разделы:
%s

Два независимых прохода по чату предложили 20+ кандидатов в новые разделы. Список
ниже: название, объём материала (strong — сообщений корпуса, где тема звучит
явно; qhits — из них вопросов), ближе всего к какому существующему разделу
(closer), что хочет включить (scope), обоснование (why).

%s

Собери из них финальный список кандидатов в НОВЫЕ разделы:
  - склей дубли и сильно перекрывающиеся кандидаты в один;
  - отсеяв то, что на самом деле является подразделом или дополнением
    существующего раздела (verdict="существующее" и укажи closer);
  - для остальных verdict="новый раздел".
  - итого не больше 12 кандидатов, сортировка по убыванию полезности.
Для каждого верни: name, verdict, closer (номер существующего раздела или 0),
parts (названия кандидатов из списка, которые вошли), scope (1-2 предложения,
что конкретно будет в разделе), why (почему это отдельный раздел), risk (чем
плох), strong (просуммируй объём склеенных кандидатов).
Отвечай только JSON-массивом объектов, без пояснений вне JSON.
"""


def cmd_consolidate(models):
    if os.path.exists(FREFINED):
        cands = json.load(io.open(FREFINED, encoding="utf-8"))
    else:
        cands = json.load(io.open(CANDSIZES, encoding="utf-8"))
    lines = []
    for c in cands:
        lines.append(u"%s | strong=%s qhits=%s closer=%s | scope: %s | why: %s" % (
            c["name"], c.get("strong"), c.get("qhits"), c.get("closer"),
            c.get("scope") or u"", c.get("why") or u""))
    prompt = CONSOLIDATE_PROMPT % (EXISTING_TXT, u"\n".join(lines))
    pool = R.Pool(models, interval=8.0)
    res = []
    for m in models:
        try:
            out = R.call(m, prompt, max_tokens=9000, tries=1)
        except Exception:
            out = None
        arr = R.last_json_array(out) if out else None
        if not arr:
            print("consolidate %s: no json" % m, flush=True)
            continue
        for it in arr:
            if isinstance(it, dict) and it.get("name"):
                it["model"] = m
                res.append(it)
        with io.open(CFINAL, "w", encoding="utf-8") as f:
            for it in res:
                f.write(json.dumps(it, ensure_ascii=False) + u"\n")
        print("consolidate %s: %d items" % (m, len(arr)), flush=True)
    print("consolidate total: %d" % len(res))
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    mode = args[0] if args else "sample"
    models = (args[1] or "").split(",") if len(args) > 1 else []
    models = [x for x in models if x]
    if mode == "fvocab":
        raise SystemExit(cmd_fvocab(int(args[1]) if len(args) > 1 else 1))
    if mode == "fbstems":
        raise SystemExit(cmd_fallback_stems(
            int(args[1]) if len(args) > 1 else 8))
    if mode == "sample":
        raise SystemExit(cmd_sample(*[int(x) for x in args[1:2]]))
    if mode == "label":
        per = int(args[2]) if len(args) > 2 else 30
        workers = int(args[3]) if len(args) > 3 else 4
        raise SystemExit(cmd_label(models or ["auto"], per=per, workers=workers))
    if mode == "merge":
        mc = int(args[2]) if len(args) > 2 else 2
        ml = int(args[3]) if len(args) > 3 else 11000
        raise SystemExit(cmd_merge(models or ["auto"], min_count=mc, maxlen=ml))
    if mode == "vocab":
        rows = [r for r in load_jsonl(LABELS) if r.get("c") == 0 and r.get("t")]
        cnt = Counter(r["t"] for r in rows)
        io.open(os.path.join(HERE, "_topics_vocab.txt"), "w",
                encoding="utf-8", newline=u"\n").write(
            u"\n".join(u"%s | %d" % tv for tv in cnt.most_common()))
        print("vocab: %d topics" % len(cnt))
        raise SystemExit(0)
    if mode == "topics":
        per = int(args[2]) if len(args) > 2 else 60
        workers = int(args[3]) if len(args) > 3 else 4
        raise SystemExit(cmd_topics(models or ["auto"], per=per,
                                    workers=workers))
    if mode == "expand":
        wrk = int(args[2]) if len(args) > 2 else 4
        mw = int(args[3]) if len(args) > 3 else MIN_LABELS
        raise SystemExit(cmd_expand(models or ["auto"], workers=wrk,
                                    min_weight=mw))
    if mode == "size":
        raise SystemExit(cmd_size())
    if mode == "rank":
        ms = int(args[2]) if len(args) > 2 else 30
        raise SystemExit(cmd_rank(models or ["auto"], min_strong=ms))
    if mode == "measure":
        raise SystemExit(cmd_measure())
    if mode == "draft":
        raise SystemExit(cmd_draft())
    if mode == "consolidate":
        raise SystemExit(cmd_consolidate(models or ["auto"]))
    print(__doc__)
    raise SystemExit(0)
