from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
NOTES = BASE / "notes"
GROUPS = BASE / "groups"
GROUPS.mkdir(parents=True, exist_ok=True)

REGION_MAP = json.loads((BASE / "regions.json").read_text(encoding="utf-8"))
# ключ raw-файла -> url: берём url прямо из конспекта, регионы ищем по нему

TOPIC_RE = re.compile(r"^[-*•\s]*(?:\[([A-Za-zА-ЯЁ_ ]+)\]|([A-Za-zА-ЯЁ_]{4,})[\s:;-])\s*(.*)$")

PLACES_TOPIC = "МЕСТА_АРХИТЕКТУРА"


def slugify(s: str) -> str:
    return re.sub(r"[()\s,./:;]+", "_", s).strip("_")


def main() -> None:
    per_topic = Counter()
    by_region: dict[str, list[str]] = defaultdict(list)
    practical: list[str] = []
    unparsed: list[str] = []
    missing_region: list[str] = []

    for f in sorted(NOTES.glob("*.md")):
        body = f.read_text(encoding="utf-8")
        url = re.match(r"#\s*(\S+)", body).group(1)
        reg = REGION_MAP.get(url)
        if reg is None:
            missing_region.append(url)
            reg = "Прочее"
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("TITLE:") or line.startswith("SRC_LEN:"):
                continue
            m = TOPIC_RE.match(line)
            if not m:
                unparsed.append(f"{reg}: {line[:120]}")
                continue
            topic = (m.group(1) or m.group(2) or "").upper().replace(" ", "_").strip("_")
            text = (m.group(3) or "").strip(" -:")
            if not topic or not text:
                unparsed.append(f"{reg}: {line[:120]}")
                continue
            per_topic[topic] += 1
            if topic == PLACES_TOPIC:
                by_region[reg].append(f"- {text}")
            else:
                practical.append(f"- [{topic}][{reg}] {text}")

    practical.sort()
    (GROUPS / "practical.txt").write_text("\n".join(practical) + "\n", encoding="utf-8")
    for reg, lines in by_region.items():
        (GROUPS / f"places__{slugify(reg)}.txt").write_text(
            f"### {reg}\n" + "\n".join(dict.fromkeys(lines)) + "\n", encoding="utf-8"
        )

    print("topics:", per_topic.most_common())
    print("practical lines:", len(practical), "chars:", sum(len(x) for x in practical))
    total_places = 0
    for reg, lines in sorted(by_region.items(), key=lambda x: -len(x[1])):
        uniq = len(dict.fromkeys(lines))
        total_places += uniq
        print(f"places {uniq:4d}/{len(lines):<4d} {sum(len(x) for x in lines):7d} ch  {reg}")
    print("places total uniq:", total_places)
    print("missing region for:", missing_region)
    print("unparsed:", len(unparsed))
    for x in unparsed[:10]:
        print("   ", x)


if __name__ == "__main__":
    main()
