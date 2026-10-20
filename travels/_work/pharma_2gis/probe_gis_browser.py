# -*- coding: utf-8 -*-
"""Разведка 2ГИС через настоящий браузер: добирается ли выдача дальше 12 карточек.

usage: python probe_gis_browser.py

HTTP-канал для 2ГИС закрыт: демо-ключ API заблокирован, а серверная выдача
2gis.tj отдаёт ровно 12 карточек и игнорирует `page`, `center`, `zoom`
(probe_pages2.py). Клиент же в браузере подгружает список скроллом через свой
бэкенд — значит полный список Душанбе (total 1084 по запросу «аптеки»)
собирается тем же приёмом, что и Яндекс-выдачи: открыть выдачу, скроллить
контейнер, копить ссылки на карточки.

Проверяет три вещи и пишет сводку в _gis_browser_probe.json:
1. не уходит ли 2gis.tj в капчу, когда его открывает реальный Chrome
   (в прошлый раз без куки браузер получал captcha.2gis.ru/form);
2. какие селекторы описывают список и карточки в текущей разметке;
3. растёт ли число ссылок `/firm/<id>` при скролле и при нажатии «Показать
   ещё» — от этого зависит, сможем ли мы снять все 1084 или только первые.
"""
import io
import json
import os
import subprocess
import time
import urllib.parse

EXE = os.path.expandvars(
    r"%APPDATA%\npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe")
HERE = os.path.dirname(os.path.abspath(__file__))
SESSION = "gispharm"

STATE = r'''(() => {
  const links = Array.from(document.querySelectorAll('a[href*="/firm/"], a[href*="/carid/"]'));
  const ids = new Set(links.map(a => (a.getAttribute('href').match(/\/(firm|carid)\/(\d+)/)||[])[2]).filter(Boolean));
  const caps = /captcha|подтвердите|Вы робот|are you a robot/i.test(document.title + ' ' + (document.body.innerText||'').slice(0,400));
  const counters = Array.from(document.querySelectorAll('[class*="total"], [class*="counter"], [data-testid]'))
      .map(e => e.tagName + '.' + (e.className||'').toString().slice(0,40) + '=' + (e.innerText||'').trim().slice(0,20))
      .filter(s => /\d/.test(s)).slice(0, 12);
  const lists = Array.from(document.querySelectorAll('ul, div'))
      .filter(e => e.querySelectorAll('a[href*="/firm/"]').length >= 3)
      .map(e => ({tag: e.tagName, cls: (e.className||'').toString().slice(0,70), kids: e.children.length,
                  n: e.querySelectorAll('a[href*="/firm/"]').length}))
      .sort((a,b) => b.n - a.n).slice(0, 6);
  const scrollers = Array.from(document.querySelectorAll('div'))
      .filter(e => e.scrollHeight > e.clientHeight + 200 && e.clientHeight > 200)
      .map(e => ({cls: (e.className||'').toString().slice(0,70), sh: e.scrollHeight, ch: e.clientHeight}))
      .sort((a,b) => b.sh - a.sh).slice(0, 5);
  const buttons = Array.from(document.querySelectorAll('button, a'))
      .map(b => (b.innerText||'').trim()).filter(t => /ещ|more|показ/i.test(t)).slice(0, 6);
  return JSON.stringify({url: location.href, title: document.title, caps: caps,
                         firm_links: links.length, firm_ids: ids.size,
                         counters: counters, lists: lists, scrollers: scrollers,
                         buttons: buttons, body: (document.body.innerText||'').replace(/\s+/g,' ').slice(0,400)});
})()'''

SCROLL = r'''(() => {
  const cand = Array.from(document.querySelectorAll('div'))
      .filter(e => e.scrollHeight > e.clientHeight + 200 && e.clientHeight > 200)
      .sort((a,b) => b.scrollHeight - a.scrollHeight)[0];
  let how = null;
  if (cand) {
    cand.scrollTop = cand.scrollTop + Math.max(400, cand.clientHeight - 80);
    how = 'container:' + (cand.className||'').toString().slice(0,40);
  } else {
    window.scrollBy(0, 1200);
    how = 'window';
  }
  const more = Array.from(document.querySelectorAll('button, a'))
      .filter(b => /ещ|показать ещё|more/i.test((b.innerText||'').trim()));
  if (more.length) { more[0].click(); how += '+clickMore'; }
  return JSON.stringify({how: how});
})()'''


def ev(js):
    p = subprocess.run([EXE, "--session", SESSION, "eval", "--stdin"],
                       input=js.encode("utf-8"), capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:300])
    v = json.loads(p.stdout.decode("utf-8", "replace").strip())
    while isinstance(v, str):
        v = json.loads(v)
    return v


def op(url):
    subprocess.run([EXE, "--session", SESSION, "open", url], capture_output=True)


def main():
    if not os.path.exists(EXE):
        sys.exit("no agent-browser exe: " + EXE)
    url = "https://2gis.tj/dushanbe/search/" + urllib.parse.quote(
        "аптеки".encode("utf-8"))
    op(url)
    timeline = []
    st = None
    for i in range(20):
        time.sleep(3)
        try:
            st = ev(STATE)
        except Exception as exc:                       # noqa: BLE001
            timeline.append({"t": i, "err": repr(exc)[:150]})
            continue
        timeline.append({"t": i, "ids": st["firm_ids"], "links": st["firm_links"],
                         "caps": st["caps"], "title": st["title"][:60]})
        print(json.dumps(timeline[-1], ensure_ascii=True))
        if st["firm_ids"] or st["caps"]:
            break
    if st is None:
        sys.exit("no state")
    print("--- loaded state ---")
    print(json.dumps(st, ensure_ascii=True, indent=1)[:4000])
    grow = []
    for i in range(14):
        try:
            r = ev(SCROLL)
        except Exception as exc:                       # noqa: BLE001
            grow.append({"t": i, "err": repr(exc)[:120]})
            break
        time.sleep(3)
        s2 = ev(STATE)
        grow.append({"t": i, "how": r.get("how"), "ids": s2["firm_ids"],
                     "links": s2["firm_links"]})
        print(json.dumps(grow[-1], ensure_ascii=True))
        if s2["firm_ids"] > 400:
            break
    io.open(os.path.join(HERE, "_gis_browser_probe.json"), "w", encoding="utf-8").write(
        json.dumps({"loaded": st, "timeline": timeline, "growth": grow,
                    "final": ev(STATE)}, ensure_ascii=True, indent=1))
    fin = ev(STATE)
    print("TOTAL ids in DOM:", fin["firm_ids"], "links:", fin["firm_links"],
          "captcha:", fin["caps"])
    print("lists:", json.dumps(fin["lists"], ensure_ascii=True)[:600])
    print("scrollers:", json.dumps(fin["scrollers"], ensure_ascii=True)[:400])
    print("buttons:", json.dumps(fin["buttons"], ensure_ascii=True)[:200])
    print("body:", json.dumps(fin["body"], ensure_ascii=True)[:600])


if __name__ == "__main__":
    import sys                                           # noqa: E402
    main()
