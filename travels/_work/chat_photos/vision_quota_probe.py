# -*- coding: utf-8 -*-
"""Лёгкий read-only пробер vision-квоты LLM-прокси.

Один мини-запрос с реальной (маленькой) картинкой к vision-модели пула, чтобы
понять, отпустил ли роутер троттлинг перед перезапуском classify_vision.py.
НИЧЕГО не пишет, процесс не трогает. Печатает одну строку статуса:
  VISION=OK  <модель> <размер_KB> ...        -> квота жива, можно рестартовать
  VISION=BLOCKED HTTP <код> ...              -> всё ещё 429/дроссель, ждать
  VISION=ERR <тип>: ...                      -> сеть/недоступность прокси
ENV: PROBE_MODEL (по умолчанию gemma-4-31b).
"""
import base64
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join("..", "travelask_chat")))
import requests  # noqa: E402
import triage    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT = os.path.abspath(os.path.join(HERE, "..", "..",
                     u"Таджикистан \U0001F1F9\U0001F1EF Чат TravelAsk"))
MODEL = os.environ.get("PROBE_MODEL", "gemma-4-31b")
MAX_BYTES = 350 * 1024  # держим зонд дешёвым: только маленькие фото


def load_done_ids():
    done = set()
    led = os.path.join(HERE, "vision_class.jsonl")
    if os.path.exists(led):
        for line in io.open(led, encoding="utf-8"):
            try:
                done.add(json.loads(line)["id"])
            except (ValueError, KeyError):
                pass
    return done


def pick_small_photo():
    """Первое существующее некрупное фото из ещё неклассифицированных."""
    ctx = os.path.join(HERE, "photo_ctx.jsonl")
    if not os.path.exists(ctx):
        return None
    done = load_done_ids()
    for line in io.open(ctx, encoding="utf-8"):
        try:
            p = json.loads(line)
        except ValueError:
            continue
        if p.get("type") == "service" or p["id"] in done:
            continue
        src = os.path.join(EXPORT, p["file"].replace("photos/", "photos" + os.sep))
        if os.path.exists(src) and os.path.getsize(src) <= MAX_BYTES:
            return src, os.path.getsize(src)
        if os.path.exists(src):  # все крупные — всё равно сгодится первый
            return src, os.path.getsize(src)
    return None


def main():
    picked = pick_small_photo()
    if not picked:
        print("VISION=ERR нет фото для зонда (photo_ctx/экспорт недоступны)")
        return 2
    src, size = picked
    b64 = base64.b64encode(open(src, "rb").read()).decode()
    content = [{"type": "text", "text": u"Что на фото? Кратко."},
               {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}]
    try:
        r = requests.post(triage.API_URL,
                          headers={"Authorization": "Bearer " + triage.key(),
                                   "Content-Type": "application/json"},
                          json={"model": MODEL, "temperature": 0, "max_tokens": 100,
                                "messages": [{"role": "user", "content": content}]},
                          timeout=120)
    except Exception as exc:  # noqa: BLE001
        print("VISION=ERR %s: %s" % (type(exc).__name__, str(exc)[:120]))
        return 3
    kb = size // 1024
    if r.status_code == 200:
        out = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or u""
        print("VISION=OK %s (%dKB) -> %s" % (MODEL, kb, repr(out[:70])))
        return 0
    print("VISION=BLOCKED HTTP %d %s" % (r.status_code, r.text[:120]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
