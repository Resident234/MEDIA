#!/bin/bash
# Watchdog: keeps candidate_analysis_worker.py running until all articles processed
cd /mnt/h/s/Work_MEDIA
VENV=$HOME/.habrvenv/bin/python

if [ ! -f "$VENV" ]; then
    python3 -m venv ~/.habrvenv 2>/dev/null || true
    ~/.habrvenv/bin/pip install -q openai requests beautifulsoup4 2>/dev/null || true
fi

while true; do
    DONE=$($VENV - <<'EOF'
import json
try:
    print(sum(1 for _ in open("candidate_results.jsonl", encoding="utf-8")))
except FileNotFoundError:
    print(0)
EOF
)
    if [ "$DONE" -ge 12038 ]; then
        echo "$(date '+%F %T') all done: $DONE" >> worker.log
        break
    fi
    echo "$(date '+%F %T') watchdog: starting worker (done=$DONE)" >> worker.log
    "$VENV" candidate_analysis_worker.py --workers 6 --batch-size 25 --start 100 >> worker.log 2>&1
    echo "$(date '+%F %T') watchdog: worker exited, restart in 30s" >> worker.log
    sleep 30
done
