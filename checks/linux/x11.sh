#!/usr/bin/env bash

set -euo pipefail

created_runner_temp=""
if [[ -z "${RUNNER_TEMP:-}" ]]; then
    RUNNER_TEMP="$(mktemp -d)"
    created_runner_temp="$RUNNER_TEMP"
fi
export RUNNER_TEMP

export DISPLAY="${DISPLAY:-:99}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-$RUNNER_TEMP/x11-runtime}"
export XDG_SESSION_TYPE=x11
unset WAYLAND_DISPLAY
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

# shellcheck disable=SC2329
cleanup() {
    if [[ -n "${xvfb_pid:-}" ]]; then
        kill "$xvfb_pid" 2>/dev/null || true
    fi
    if [[ -n "$created_runner_temp" ]]; then
        rm -rf "$created_runner_temp"
    fi
}
trap cleanup EXIT

Xvfb "$DISPLAY" -screen 0 1280x1024x24 -nolisten tcp >"$RUNNER_TEMP/xvfb.log" 2>&1 &
xvfb_pid="$!"
display_number="${DISPLAY#:}"
display_number="${display_number%%.*}"

for _ in {1..30}; do
    if [[ -S "/tmp/.X11-unix/X${display_number}" ]]; then
        timeout "${PASTY_TEST_TIMEOUT:-25m}" mise run test clipboard "${PASTY_CLIPBOARD_SCENARIO:-all}"
        exit 0
    fi
    sleep 0.2
done

cat "$RUNNER_TEMP/xvfb.log" >&2
echo "Xvfb did not start." >&2
exit 1
