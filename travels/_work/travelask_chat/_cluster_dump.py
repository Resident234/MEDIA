# -*- coding: utf-8 -*-
"""Читаемая сводка кластеров: имя | вес | темы | корни. Только для глаз."""
import io
import os

import _cluster_llm as C

OUT = os.path.join(C.HERE, "_clusters_new.txt")


def main():
    cl = C.clusters_from_labels()
    lines = []
    for c in cl:
        lines.append(u"%s | w=%d (lab=%d free=%d) | %s" % (
            c["name"], c["weight"], c["nlab"], c["nfree"],
            u", ".join(u"%s:%d" % tv for tv in c["topics"][:8])))
        if c.get("stems"):
            lines.append(u"    stems: %s" % u", ".join(c["stems"]))
    io.open(OUT, "w", encoding="utf-8", newline=u"\n").write(
        u"\n".join(lines) + u"\n")
    print("clusters: %d, with stems: %d, lines: %d" % (
        len(cl), sum(1 for c in cl if c.get("stems")), len(lines)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
