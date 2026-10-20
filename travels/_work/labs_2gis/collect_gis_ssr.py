# -*- coding: utf-8 -*-
"""Съём выдачи 2ГИС по лабораториям/анализам (Душанбе, SSR-поиск).

usage:
  python collect_gis_ssr.py            # обычная работа
  python collect_gis_ssr.py --dry      # только показать, что уже снято

Канал и логика те же, что в pharma_2gis/collect_gis_ssr.py: один запрос —
12 карточек, полный список собирается шириной по `_queries.txt`.
Отличие — фильтр «что считать лабораторией»: совпадение по названию/сети
(`лаборатор/анализ/диагност/ПЦР/ИФА/ozmu/таҳлил/check-up/обследovan/
медосмотр`) или рубрике, содержащей `лаборатори`/`анализ`/`диагност`.
"""
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pharma_2gis"))
import gis_state  # noqa: E402

QUERIES = os.path.join(HERE, "_queries.txt")
ROWS = os.path.join(HERE, "rows.jsonl")
LOG = os.path.join(HERE, "collect.log")
CITY = "dushanbe"
SLEEP = 1.5
STALE_LIMIT = 40

LAB_KEYS = (u"лаборатор", u"анализ", u"диагност", u"пцр", u"ифа",
            u"check-up", u"чек-ап", u"обследование", u"медосмотр",
            u"таҳлил", u"озмуни", u"laborator", u"diagnost")


def a(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def is_lab(rubrics, name, org_name):
    for r in rubrics or []:
        rl = (r or "").lower()
        if any(k in rl for k in LAB_KEYS):
            return True
    text = ((name or "") + " " + (org_name or "")).lower()
    return any(k in text for k in LAB_KEYS)


def load_queries():
    return [l.strip() for l in io.open(QUERIES, encoding="utf-8") if l.strip()]


def done_set():
    if not os.path.exists(LOG):
        return set()
    out = set()
    for l in io.open(LOG, encoding="utf-8"):
        parts = l.rstrip("\n").split("\t")
        if len(parts) >= 1 and parts[0].startswith("Q "):
            out.add(parts[0][2:])
    return out


def seen_ids():
    ids = set()
    if not os.path.exists(ROWS):
        return ids
    for l in io.open(ROWS, encoding="utf-8"):
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if r.get("id"):
            ids.add(str(r["id"]))
    return ids


def weekday_hours(sch):
    if not isinstance(sch, dict):
        return {}
    out = {}
    for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
        v = sch.get(day)
        if not isinstance(v, dict):
            continue
        wh = v.get("working_hours")
        if isinstance(wh, list):
            out[day] = [{"from": x.get("from"), "to": x.get("to")}
                        for x in wh if isinstance(x, dict)]
        elif isinstance(wh, dict):
            out[day] = [{"from": wh.get("from"), "to": wh.get("to")}]
    return out


def compact_item(iid, d, q):
    addr = d.get("address") or {}
    street_number = None
    if isinstance(addr, dict):
        for c in addr.get("components") or []:
            if c.get("type") in ("street_number", "street"):
                street_number = (c.get("street") or "") + (
                    (", " + c.get("number")) if c.get("number") else "")
                break
    district = None
    for x in d.get("adm_div") or []:
        if x.get("type") == "district":
            district = x.get("name")
            break
    sch = d.get("schedule") or {}
    point = d.get("point") or {}
    org = d.get("org") or {}
    rubrics = [r.get("name") for r in d.get("rubrics") or []
               if isinstance(r, dict) and r.get("name")]
    attrs = []
    for g in d.get("attribute_groups") or []:
        if isinstance(g, dict) and g.get("name"):
            attrs.append(g["name"])
    return {
        "id": str(iid),
        "name": d.get("name"),
        "org_name": org.get("name") or org.get("primary"),
        "branch_count": org.get("branch_count"),
        "poi_category": d.get("poi_category"),
        "rubrics": rubrics,
        "is_lab": is_lab(rubrics, d.get("name"),
                         org.get("name") or org.get("primary")),
        "address_name": d.get("address_name"),
        "street_number": street_number,
        "district": district,
        "lon": point.get("lon"),
        "lat": point.get("lat"),
        "is_24x7": bool(sch.get("is_24x7")) if isinstance(sch, dict) else None,
        "working_hours": weekday_hours(sch),
        "rating": d.get("org_rating"),
        "review_count": d.get("org_review_count"),
        "attribute_groups": attrs,
        "url_2gis": "https://2gis.tj/%s/firm/%s" % (CITY, iid),
        "first_seen_query": q,
    }


def log(msg):
    line = "[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    sys.stdout.write(a(line))
    sys.stdout.flush()
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(line)


def run_query(q):
    url = gis_state.search_url(CITY, q)
    status, body = gis_state.fetch(url, tries=3, pause=SLEEP)
    if status != "fresh" or not body:
        return [], None, str(status)
    st = gis_state.state_of(body)
    if not st:
        return [], None, "no_state"
    items = gis_state.items_of(st)
    total = gis_state.total_of(st)
    return items, total, None


def main():
    dry = "--dry" in sys.argv
    qs = load_queries()
    done = done_set()
    ids = seen_ids()
    log("start: queries=%d done=%d rows=%d" % (len(qs), len(done), len(ids)))
    if dry:
        log("dry run only")
        return
    stale = 0
    with io.open(ROWS, "a", encoding="utf-8") as rf:
        for idx, q in enumerate(qs):
            if q in done:
                continue
            items, total, err = run_query(q)
            added = 0
            for iid, d in items:
                key = str(iid)
                if key in ids:
                    continue
                row = compact_item(iid, d, q)
                rf.write(json.dumps(row, ensure_ascii=False) + "\n")
                rf.flush()
                ids.add(key)
                added += 1
            log("Q %s\t+%d\tU%d\tT%s\t%s" % (
                q, added, len(ids), total, err or ""))
            if added == 0:
                stale += 1
            else:
                stale = 0
            if stale >= STALE_LIMIT:
                log("stale %d queries without new ids, stop" % stale)
                break
            time.sleep(SLEEP)
    log("finish: union=%d" % len(ids))


if __name__ == "__main__":
    main()
