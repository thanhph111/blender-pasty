import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from checks.clipboard.scenarios import COPIED_FILE_FIXTURES, SCENARIOS

CLIPBOARD_TIMEOUT_SECONDS = 120
CLIPBOARD_RELEASE_TIMEOUT_SECONDS = 10
WAYLAND_INPUT_SIGNAL_ATTEMPTS = 5
WAYLAND_INPUT_SETTLE_SECONDS = 0.2


def main() -> None:
    parser = argparse.ArgumentParser(prog="clipboard run", description="Run live clipboard tests")
    parser.add_argument("scenario", nargs="?", choices=("all", *SCENARIOS), default="all")
    args = parser.parse_args()

    test_clipboard(args.scenario)


def test_clipboard(scenario: str) -> None:
    blender_bin = os.environ.get("BLENDER_BIN") or shutil.which("blender")
    if not blender_bin:
        msg = "Blender not found. Set BLENDER_BIN or put blender on PATH."
        raise RuntimeError(msg)

    scenarios = SCENARIOS if scenario == "all" else (scenario,)
    for current_scenario in scenarios:
        test_clipboard_scenario(blender_bin, current_scenario)


def test_clipboard_scenario(blender_bin: str, scenario: str) -> None:
    run_clipboard_os("clear")
    try:
        if scenario == "copied-files":
            run_clipboard_os("seed-files", *COPIED_FILE_FIXTURES)
            run_clipboard_os("expect-files", *COPIED_FILE_FIXTURES)
            run_clipboard_blender(blender_bin, scenario)
        elif scenario == "paste-image":
            run_clipboard_os("seed-png", COPIED_FILE_FIXTURES[0])
            run_clipboard_os("expect-image")
            run_clipboard_blender(blender_bin, scenario)
        elif scenario == "copy-image":
            run_clipboard_blender_copy_and_verify(blender_bin, scenario)
    finally:
        run_clipboard_os("clear")


def run_clipboard_blender(blender_bin: str, scenario: str) -> None:
    with TemporaryDirectory(prefix="pasty-clipboard-result-") as temp_dir:
        result_path = Path(temp_dir) / "result.json"
        env = os.environ.copy()
        env["PASTY_CLIPBOARD_RESULT"] = str(result_path)
        exit_code = run_blender_for_clipboard(
            blender_bin,
            env,
            result_path,
            *blender_clipboard_args(scenario),
            timeout=CLIPBOARD_TIMEOUT_SECONDS,
        )
        check_clipboard_result(result_path)
        if exit_code != 0:
            msg = f"Blender exited with code {exit_code} after writing a successful result."
            raise RuntimeError(msg)


def run_clipboard_blender_copy_and_verify(blender_bin: str, scenario: str) -> None:
    with TemporaryDirectory(prefix="pasty-clipboard-result-") as temp_dir:
        result_path = Path(temp_dir) / "result.json"
        input_ready_path = Path(temp_dir) / "input-ready"
        input_sent_path = Path(temp_dir) / "input-sent"
        release_path = Path(temp_dir) / "release"
        env = os.environ.copy()
        env["PASTY_CLIPBOARD_RESULT"] = str(result_path)
        env["PASTY_CLIPBOARD_RELEASE"] = str(release_path)
        needs_wayland_input_signal = wayland_clipboard_input_signal_needed()
        if needs_wayland_input_signal and not wayland_clipboard_input_signal_tools():
            msg = "Wayland copy-image checks need wtype or ydotool to send a GUI input event."
            raise RuntimeError(msg)
        if needs_wayland_input_signal:
            env["PASTY_CLIPBOARD_INPUT_READY"] = str(input_ready_path)
            env["PASTY_CLIPBOARD_INPUT_SENT"] = str(input_sent_path)
        process = start_blender(blender_bin, env, *blender_clipboard_args(scenario))
        try:
            if needs_wayland_input_signal:
                wait_for_file(
                    input_ready_path,
                    process,
                    "Blender did not become ready for the Wayland input event.",
                )
                focus_wayland_blender_window(process)
                send_wayland_clipboard_input_signal()
                time.sleep(WAYLAND_INPUT_SETTLE_SECONDS)
                input_sent_path.write_text("sent", encoding="utf-8")
            wait_for_clipboard_result(result_path, process)
            check_clipboard_result(result_path)
            run_clipboard_os("expect-image")
        finally:
            release_path.write_text("done", encoding="utf-8")
            wait_for_blender_to_exit(process)


def blender_clipboard_args(scenario: str) -> list[str]:
    return [
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(ROOT / "checks" / "clipboard" / "blender.py"),
        "--",
        scenario,
    ]


def check_clipboard_result(result_path: Path) -> None:
    if not result_path.is_file():
        msg = "Blender clipboard check did not write a result before exiting."
        raise RuntimeError(msg)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("ok"):
        return
    msg = result.get("error") or "Blender clipboard check failed."
    traceback_text = result.get("traceback")
    if traceback_text:
        msg = f"{msg}\n{traceback_text}"
    raise RuntimeError(msg)


def run_clipboard_os(command: str, *args: Path | str) -> None:
    run([sys.executable, str(ROOT / "checks" / "clipboard" / "os.py"), command, *map(str, args)])


def run_blender_for_clipboard(
    blender_bin: str, env: dict[str, str], result_path: Path, *args: str, timeout: int | None = None
) -> int:
    command = [blender_bin, *args]
    print(" ".join(command), flush=True)
    try:
        result = subprocess.run(command, check=False, cwd=ROOT, env=env, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        msg = f"Blender did not finish within {timeout} seconds."
        raise RuntimeError(msg) from error

    if result.returncode != 0 and not result_path.is_file():
        msg = (
            f"Blender clipboard check exited with code {result.returncode} "
            "without writing a result."
        )
        raise RuntimeError(msg)
    return result.returncode


def start_blender(blender_bin: str, env: dict[str, str], *args: str) -> subprocess.Popen[bytes]:
    command = [blender_bin, *args]
    print(" ".join(command), flush=True)
    return subprocess.Popen(command, cwd=ROOT, env=env)


def wayland_clipboard_input_signal_needed() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY"))


def wayland_clipboard_input_signal_tools() -> tuple[str, ...]:
    tools = []
    if shutil.which("wtype") is not None:
        tools.append("wtype")
    if shutil.which("ydotool") is not None:
        tools.append("ydotool")
    return tuple(tools)


def focus_wayland_blender_window(process: subprocess.Popen[bytes]) -> None:
    if shutil.which("swaymsg") is None:
        time.sleep(1)
        return

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        tree = sway_tree()
        node = sway_node_for_process(tree, process.pid) if tree is not None else None
        if node is not None:
            node_id = node.get("id")
            if isinstance(node_id, int):
                subprocess.run(
                    ["swaymsg", f"[con_id={node_id}]", "focus"],
                    check=False,
                    cwd=ROOT,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                print(f"Focused Sway window for Blender pid {process.pid}.", flush=True)
                time.sleep(0.5)
                return
        if process.poll() is not None:
            return
        time.sleep(0.2)

    print("Could not find Blender in the Sway tree before sending input.", flush=True)
    time.sleep(1)


def sway_tree() -> dict[str, object] | None:
    try:
        result = subprocess.run(
            ["swaymsg", "-t", "get_tree"],
            check=False,
            capture_output=True,
            cwd=ROOT,
            encoding="utf-8",
            errors="replace",
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        tree = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return tree if isinstance(tree, dict) else None


def sway_node_for_process(tree: dict[str, object], pid: int) -> dict[str, object] | None:
    fallback = None
    for node in walk_sway_nodes(tree):
        if node.get("pid") == pid:
            return node
        name = node.get("name")
        app_id = node.get("app_id")
        if fallback is None and (
            (isinstance(name, str) and "blender" in name.lower())
            or (isinstance(app_id, str) and "blender" in app_id.lower())
        ):
            fallback = node
    return fallback


def walk_sway_nodes(node: dict[str, object]) -> Generator[dict[str, object], None, None]:
    yield node
    for key in ("nodes", "floating_nodes"):
        children = node.get(key)
        if not isinstance(children, list):
            continue
        for child in children:
            if isinstance(child, dict):
                yield from walk_sway_nodes(cast("dict[str, object]", child))


def send_wayland_clipboard_input_signal() -> None:
    tools = wayland_clipboard_input_signal_tools()
    if not tools:
        msg = "No supported Wayland input command found for the clipboard check."
        raise RuntimeError(msg)

    any_sent = False
    for attempt in range(WAYLAND_INPUT_SIGNAL_ATTEMPTS):
        for tool in tools:
            if tool == "wtype":
                sent = send_wayland_input(["wtype", "-k", "a"])
            elif tool == "ydotool":
                sent = send_wayland_input(["ydotool", "key", "30:1", "30:0"])
            else:
                continue
            any_sent = any_sent or sent
        if attempt < WAYLAND_INPUT_SIGNAL_ATTEMPTS - 1:
            time.sleep(0.4)

    if not any_sent:
        msg = "Wayland input commands were available, but none could send a GUI input event."
        raise RuntimeError(msg)


def send_wayland_input(command: list[str]) -> bool:
    result = subprocess.run(command, check=False, cwd=ROOT)
    if result.returncode == 0:
        return True
    print(f"Wayland input command failed with code {result.returncode}: {command[0]}", flush=True)
    return False


def wait_for_file(result_path: Path, process: subprocess.Popen[bytes], message: str) -> None:
    deadline = time.monotonic() + CLIPBOARD_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if result_path.is_file():
            return
        if process.poll() is not None:
            break
        time.sleep(0.1)

    if result_path.is_file():
        return

    if process.poll() is None:
        process.terminate()
    exit_code = process.poll()
    if exit_code is not None:
        message = f"{message} Blender exited with code {exit_code}."
    raise RuntimeError(message)


def wait_for_clipboard_result(result_path: Path, process: subprocess.Popen[bytes]) -> None:
    wait_for_file(result_path, process, "Blender clipboard check did not write a result.")


def wait_for_blender_to_exit(process: subprocess.Popen[bytes]) -> None:
    try:
        exit_code = process.wait(timeout=CLIPBOARD_RELEASE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=CLIPBOARD_RELEASE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        msg = "Blender did not exit after clipboard verification release."
        raise RuntimeError(msg) from None
    if exit_code != 0:
        sys.exit(exit_code)


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
