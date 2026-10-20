#!/bin/sh
# Headed probe of 2GIS web cards: root first, then one firm card, then the extractor.
cd /h/s/Work_MEDIA/travels/_work/fitness_2gis || exit 1
export AGENT_BROWSER_SESSION=tjgym2
export AGENT_BROWSER_RESTORE=tjgym2
export PYTHONIOENCODING=utf-8

echo "--- STEP open root (headed)"
agent-browser --headed open "https://2gis.tj/dushanbe/" 2>&1 | tail -4
agent-browser wait --load networkidle 2>&1 | tail -2
echo "URL_ROOT=$(agent-browser get url 2>&1 | tail -1)"
echo "TITLE_ROOT=$(agent-browser get title 2>&1 | tail -1)"

echo "--- STEP open card"
agent-browser navigate "https://2gis.tj/dushanbe/firm/70000001103044666" 2>&1 | tail -3
agent-browser wait --load networkidle 2>&1 | tail -2
echo "URL_CARD=$(agent-browser get url 2>&1 | tail -1)"
echo "TITLE_CARD=$(agent-browser get title 2>&1 | tail -1)"

echo "--- STEP eval"
agent-browser eval "$(cat extract_card.js)" 2>&1 | tail -c 2000

echo "--- STEP cookies"
agent-browser cookies get 2>&1 | tail -c 600
