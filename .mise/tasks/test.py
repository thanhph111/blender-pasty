#!/usr/bin/env -S uv run -s --no-sync

# [MISE] description="Run tests"
# [USAGE] arg "[area]" help="Test area" {
# [USAGE]   choices "source" "package" "clipboard" "linux"
# [USAGE]   default "source"
# [USAGE] }
# [USAGE] arg "[name]" help="Clipboard scenario or Linux session" {
# [USAGE]   choices "all" "copied-files" "paste-image" "copy-image" "x11" "wayland"
# [USAGE] }
# [USAGE] arg "[scenario]" help="Linux clipboard scenario" {
# [USAGE]   choices "all" "copied-files" "paste-image" "copy-image"
# [USAGE] }

# This dispatcher runs repo check scripts and leaves command output visible.
# ruff: noqa: S603

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(prog="test", description="Run tests")
    parser.add_argument("area", nargs="?", choices=("source", "package", "clipboard", "linux"))
    parser.add_argument("name", nargs="?")
    parser.add_argument("scenario", nargs="?")
    args = parser.parse_args()

    area = args.area or "source"
    if area == "source":
        reject_extra_args(args.name, args.scenario, "source")
        run([sys.executable, "checks/addon/source.py"])
    elif area == "package":
        reject_extra_args(args.name, args.scenario, "package")
        run([sys.executable, "checks/addon/package.py"])
    elif area == "clipboard":
        reject_extra_args(args.scenario, None, "clipboard")
        run(optional_arg_command("checks/clipboard/run.py", args.name))
    elif area == "linux":
        run(optional_arg_command("checks/linux/run.py", args.name, args.scenario))


def optional_arg_command(script: str, *args: str | None) -> list[str]:
    return [sys.executable, script, *(arg for arg in args if arg is not None)]


def reject_extra_args(first: str | None, second: str | None, area: str) -> None:
    if first is None and second is None:
        return
    msg = f"{area} tests do not take extra arguments"
    raise RuntimeError(msg)


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
