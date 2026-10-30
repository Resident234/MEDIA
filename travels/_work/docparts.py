# -*- coding: utf-8 -*-
"""Полный текст разбитого справочника: вступление + все части, без оглавления-таблицы."""
from pathlib import Path

BASE = Path(__file__).resolve().parent
TRAVELS = BASE.parent


def read_all() -> str:
    head = (BASE / "build" / "00_head.md").read_text(encoding="utf-8").strip()
    parts = [p.read_text(encoding="utf-8").strip()
             for p in sorted(TRAVELS.glob("Таджикистан_*.md"))]
    return "\n\n".join([head] + parts)
