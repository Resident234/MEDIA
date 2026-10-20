# -*- coding: utf-8 -*-
"""One-shot look at a Yandex Maps page: python peek.py [url] [wait_seconds]."""
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import yxd  # noqa: E402

JS = io.open(os.path.join(HERE, "_state.js"), encoding="utf-8").read()


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else None
    wait = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    if url:
        yxd.op(url)
    time.sleep(wait)
    st = yxd.ev(JS)
    # Names are Cyrillic: print them ASCII-escaped so the cp866 console survives.
    print(json.dumps({"session": yxd.SESSION, "snippets": st["snippets"],
                      "orgLinks": st["orgLinks"], "scroll": st["scroll"],
                      "cats": st["cats"], "url": st["url"][:150],
                      "names": [json.dumps(n, ensure_ascii=True) for n in st["names"]],
                      "coords": st["coords"],
                      "text": json.dumps(st["text"], ensure_ascii=True)[:400]},
                     ensure_ascii=True, indent=1))


if __name__ == "__main__":
    main()
