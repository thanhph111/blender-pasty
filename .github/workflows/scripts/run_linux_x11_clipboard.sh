#!/usr/bin/env bash

set -euo pipefail

export DISPLAY=:99

Xvfb "$DISPLAY" -screen 0 1280x1024x24 -nolisten tcp >"$RUNNER_TEMP/xvfb.log" 2>&1 &
xvfb_pid="$!"
trap 'kill "$xvfb_pid" 2>/dev/null || true' EXIT

for _ in {1..30}; do
    if [ -S /tmp/.X11-unix/X99 ]; then
        break
    fi
    sleep 0.2
done

timeout 25m mise run test clipboard all
