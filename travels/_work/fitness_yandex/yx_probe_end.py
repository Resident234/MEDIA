# -*- coding: utf-8 -*-
"""Run the completeness probe (yx_end.js) on one of the two searches."""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yx_grab as g


def main():
    qline = sys.argv[1]
    out = sys.argv[2]
    q = io.open(os.path.join(g.HERE, "_q.txt"), encoding="utf-8").read().splitlines()[int(qline) - 1].strip()
    g.wait_ready("yxm", g.BASE.format(q=q))
    js = io.open(os.path.join(g.HERE, "yx_end.js"), encoding="utf-8").read()
    res = g.eval_js("yxm", js)
    io.open(out, "w", encoding="utf-8").write(json.dumps(res, ensure_ascii=False, indent=1))
    print("wrote %s: rendered=%s scroll=%s" % (out, res.get("rendered"), res.get("scroll")))


if __name__ == "__main__":
    main()
