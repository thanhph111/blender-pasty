#!/usr/bin/env bash

set -euo pipefail

session="${1:?usage: checks/linux/docker.sh x11|wayland [scenario]}"
scenario="${2:-${PASTY_CLIPBOARD_SCENARIO:-all}}"
version="${PASTY_BLENDER_VERSION:-5.1}"

mise run blender install "$version"
export BLENDER_BIN
BLENDER_BIN="$(mise run --quiet blender path "$version")"
export PASTY_CLIPBOARD_SCENARIO="$scenario"

case "$session" in
    x11)
        exec checks/linux/x11.sh
        ;;
    wayland)
        exec checks/linux/wayland.sh
        ;;
    *)
        echo "Unknown Linux clipboard session: $session" >&2
        exit 1
        ;;
esac
