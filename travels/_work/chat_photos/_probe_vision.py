# -*- coding: utf-8 -*-
"""Опрос vision-способности каждой живой модели локального эндпоинта.

Для каждой модели шлёт реальное небольшое фото из экспорта + текст-запрос.
Классифицирует ответ: vision_ok (200 + осмысленное описание), no_vision
(400/ошибка про image/vision/не поддерживает), throttled (429), или unknown.
"""
import base64
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join("..", "travelask_chat")))
import requests  # noqa: E402
import triage    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT = os.path.abspath(os.path.join(HERE, "..", "..",
                     u"Таджикистан \U0001F1F9\U0001F1EF Чат TravelAsk"))
BASE = triage.API_URL.rsplit("/chat/", 1)[0]

PROMPT = (u"Что изображено на этой картинке? Ответь ОДНИМ словом. "
          u"Если изображения нет или ты его не видишь — ответь ровно: NOIMAGE")


def pick_photo():
    d = os.path.join(EXPORT, "photos")
    for name in sorted(os.listdir(d)):
        if name.endswith(".jpg") and "_thumb" not in name:
            p = os.path.join(d, name)
            if 3000 < os.path.getsize(p) < 200000:   # компактное, чтобы быстрый промпт
                return p
    return None


def probe(model, b64):
    content = [{"type": "text", "text": PROMPT},
               {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}]
    try:
        r = requests.post(triage.API_URL,
                          headers={"Authorization": "Bearer " + triage.key(),
                                   "Content-Type": "application/json"},
                          json={"model": model, "temperature": 0, "max_tokens": 24,
                                "messages": [{"role": "user", "content": content}]},
                          timeout=120)
    except Exception as exc:  # noqa: BLE001
        return "ERR", type(exc).__name__ + ": " + str(exc)[:120]
    if r.status_code == 429:
        return "THROTTLED", r.text[:120]
    if r.status_code != 200:
        t = r.text.lower()
        blob = ("image" in t or "vision" in t or "modalit" in t
                or "does not support" in t or "not support" in t)
        return ("NO_VISION" if blob else "HTTP_%d" % r.status_code), r.text[:140]
    out = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if not out.strip() or "NOIMAGE" in out.upper():
        return "NO_VISION", out.strip()[:120]
    return "VISION_OK", out.strip()[:120]


def main():
    models = [m.strip() for m in (sys.argv[1].split(",") if len(sys.argv) > 1 else []) if m.strip()]
    if not models:
        try:
            j = requests.get(BASE + "/models",
                             headers={"Authorization": "Bearer " + triage.key()}, timeout=30).json()
            models = [m.get("id") for m in j.get("data", []) if m.get("id")]
        except Exception as exc:  # noqa: BLE001
            print("list failed:", exc)
            return 1
    path = pick_photo()
    b64 = base64.b64encode(open(path, "rb").read()).decode() if path else ""
    print("photo:", os.path.basename(path) if path else "(none)", "b64len:", len(b64))
    for m in models:
        if not b64:
            print("%-28s NO-PHOTO" % m)
            continue
        verdict, info = probe(m, b64)
        print("%-28s %-11s %s" % (m, verdict, info.replace("\n", " ")))
        time.sleep(2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
