#!/usr/bin/env bash

set -euo pipefail

sway_pid=""
ydotoold_pid=""

main() {
    configure_wayland_environment
    write_sway_config
    trap dump_logs_and_stop EXIT
    start_ydotoold_if_possible
    start_sway
    print_sway_diagnostics
    verify_wayland_clipboard
    eglinfo --wayland >"$RUNNER_TEMP/eglinfo.log" 2>&1 || true
    mise run test clipboard all
}

configure_wayland_environment() {
    export XDG_RUNTIME_DIR="$RUNNER_TEMP/wayland-runtime"
    mkdir -p "$XDG_RUNTIME_DIR"
    chmod 700 "$XDG_RUNTIME_DIR"

    export WAYLAND_DISPLAY=wayland-1
    export WLR_BACKENDS=headless,libinput
    export WLR_LIBINPUT_NO_DEVICES=1
    export WLR_RENDERER=pixman
    export LIBSEAT_BACKEND=noop
    export XDG_CURRENT_DESKTOP=sway
    export LIBGL_ALWAYS_SOFTWARE=1
    export GALLIUM_DRIVER=llvmpipe
    export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
    export __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json
}

write_sway_config() {
    cat >"$RUNNER_TEMP/sway.config" <<'EOF'
xwayland disable
output HEADLESS-1 resolution 1280x1024 position 0,0
seat seat0 xcursor_theme Adwaita 24
default_border none
EOF
}

dump_logs_and_stop() {
    status="$?"
    if [ "$status" -ne 0 ]; then
        for log in "$RUNNER_TEMP/sway.log" "$RUNNER_TEMP/ydotoold.log" "$RUNNER_TEMP/eglinfo.log"; do
            if [ -f "$log" ]; then
                echo "::group::$(basename "$log")"
                cat "$log"
                echo "::endgroup::"
            fi
        done
    fi

    if [ -n "$ydotoold_pid" ]; then
        sudo kill "$ydotoold_pid" 2>/dev/null || true
    fi
    if [ -n "$sway_pid" ]; then
        kill "$sway_pid" 2>/dev/null || true
    fi
}

start_ydotoold_if_possible() {
    sudo modprobe uinput || true
    if [ ! -e /dev/uinput ]; then
        echo "/dev/uinput is not available; continuing with Wayland virtual-keyboard input only."
        return
    fi

    sudo chmod 666 /dev/uinput
    export YDOTOOL_SOCKET=/tmp/.ydotool_socket
    sudo rm -f "$YDOTOOL_SOCKET"
    sudo sh -c 'exec ydotoold > "$1" 2>&1' sh "$RUNNER_TEMP/ydotoold.log" &
    ydotoold_pid="$!"

    for _ in {1..30}; do
        if [ -S "$YDOTOOL_SOCKET" ]; then
            sudo chmod 666 "$YDOTOOL_SOCKET"
            sudo chmod -R a+rw /dev/input /dev/uinput 2>/dev/null || true
            return
        fi
        sleep 0.2
    done
}

start_sway() {
    sway -c "$RUNNER_TEMP/sway.config" -d >"$RUNNER_TEMP/sway.log" 2>&1 &
    sway_pid="$!"

    for _ in {1..30}; do
        if [ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]; then
            return
        fi
        sleep 1
    done

    cat "$RUNNER_TEMP/sway.log"
    exit 1
}

print_sway_diagnostics() {
    swaysock=""
    for _ in {1..30}; do
        swaysock="$(find "$XDG_RUNTIME_DIR" -maxdepth 1 -type s -name 'sway-ipc*.sock' -print -quit || true)"
        if [ -n "$swaysock" ]; then
            break
        fi
        sleep 0.2
    done

    if [ -n "$swaysock" ]; then
        export SWAYSOCK="$swaysock"
        swaymsg -t get_outputs || true
        swaymsg -t get_seats || true
    else
        echo "Sway IPC socket is not available; continuing with the Wayland clipboard check."
    fi
}

verify_wayland_clipboard() {
    printf 'pasty-wayland-check' | wl-copy --type text/plain
    test "$(wl-paste --no-newline --type text/plain)" = 'pasty-wayland-check'
}

main "$@"
