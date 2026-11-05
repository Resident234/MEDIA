# -*- coding: utf-8 -*-
"""Проверка: годятся ли конкретные vision-модели для Stage B (JSON-промпт).

Берёт реальные безымянные фото из photo_ctx и для каждой модели шлёт ТОТ ЖЕ
промпт, что classify_vision, затем парсит ответ как JSON. Пишет entity/named/
category — чтобы понять, выдаёт ли модель разбор и разумные имена. В ledger НЕ
пишет (тест изолирован от фонового vision-процесса).
"""
import base64
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join("..", "travelask_chat")))
import triage    # noqa: E402
import requests  # noqa: E402
from classify_vision import PROMPT, EXPORT  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def vcall(model, prompt, b64):
    content = [{"type": "text", "text": prompt},
               {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}]
    r = requests.post(triage.API_URL,
                      headers={"Authorization": "Bearer " + triage.key(),
                               "Content-Type": "application/json"},
                      json={"model": model, "temperature": 0, "max_tokens": 500,
                            "messages": [{"role": "user", "content": content}]},
                      timeout=180)
    if r.status_code != 200:
        return None, "HTTP %d %s" % (r.status_code, r.text[:120])
    out = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return out, None


def jparse(txt):
    m = re.search(r"\{.*\}", txt or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


def main():
    models = sys.argv[1].split(",")
    rows = [json.loads(l) for l in io.open(os.path.join(HERE, "photo_ctx.jsonl"), encoding="utf-8")]
    # возьмём фото, где в подписи явно есть слово (чтобы был эталон для сверки)
    sample = [r for r in rows if (r.get("caption") or "")][:4]
    for model in models:
        print("==== %s ====" % model)
        for r in sample:
            src = os.path.join(EXPORT, r["file"].replace("photos/", u"photos" + os.sep))
            if not os.path.exists(src):
                continue
            b64 = base64.b64encode(open(src, "rb").read()).decode()
            pr = PROMPT.format(caption=r.get("caption") or u"(нет)",
                               before=u" | ".join(r.get("ctx_before") or [u"-"])[:600],
                               after=u" | ".join(r.get("ctx_after") or [u"-"])[:600])
            txt, err = vcall(model, pr, b64)
            if err:
                print("  id=%s ERR %s" % (r["id"], err)); time.sleep(2); continue
            obj = jparse(txt)
            cap = (r.get("caption") or "")[:40].replace("\n", " ")
            if obj is None:
                print("  id=%s NOJSON len=%d head=%r" % (r["id"], len(txt), txt[:60]))
            else:
                print("  id=%s named=%s entity=%r cat=%r | cap=%r"
                      % (r["id"], obj.get("named"), obj.get("entity"), obj.get("category"), cap))
            time.sleep(2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
