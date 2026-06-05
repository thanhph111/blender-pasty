#!/usr/bin/env python3

import argparse
import json
import os
import sys
from pathlib import Path
from typing import NoReturn


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan GitHub Actions matrix targets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    headless = subparsers.add_parser("headless", help="Plan headless Blender targets")
    headless.add_argument("--profile", choices=("fast", "full"), required=True)

    clipboard = subparsers.add_parser("clipboard", help="Plan live clipboard targets")
    clipboard.add_argument("--profile", choices=("fast", "full"), required=True)

    args = parser.parse_args()

    if args.command == "headless":
        matrix = headless_matrix(args.profile)
    elif args.command == "clipboard":
        matrix = clipboard_matrix(args.profile)
    else:
        parser.error(f"unknown command: {args.command}")

    write_github_output("matrix", json.dumps(matrix, separators=(",", ":")))


def headless_matrix(profile: str) -> dict[str, list[dict[str, str]]]:
    if profile == "fast":
        targets = ["Linux, Blender 4.2", "Linux, Blender 5.1"]
    else:
        targets = [
            f"{platform}, Blender {blender}"
            for platform in ("Linux", "Windows", "macOS")
            for blender in ("4.2", "4.5", "5.1")
        ]

    # GitHub's sidebar can collapse matrix rows down to one matrix value.
    # Keep that value fully descriptive so repeated 4.2/4.5/5.1 rows stay readable.
    return {"include": [{"target": target} for target in targets]}


def clipboard_matrix(profile: str) -> dict[str, list[dict[str, str]]]:
    sessions = [
        ("Linux X11 clipboard", "ubuntu-24.04", "linux-x11", "linux"),
        ("Linux Wayland clipboard", "ubuntu-24.04", "linux-wayland", "linux"),
    ]

    if profile == "fast":
        targets = [("Linux X11 clipboard", "ubuntu-24.04", "linux-x11", "linux", "5.1")]
    else:
        targets = []
        for session in sessions:
            blenders = ("4.2", "4.5", "5.1")
            if session[2] == "linux-wayland":
                # Blender 4.5 exits in hosted headless Sway during image paste
                # before Pasty can write a result. Keep 4.5 covered by X11 live
                # checks and headless Wayland-free checks.
                blenders = ("4.2", "5.1")
            targets.extend((*session, blender) for blender in blenders)

    return {
        "include": [
            {
                "label": f"{label}, Blender {blender}",
                "runner": runner,
                "session": session,
                "blender": blender,
                "cache_key": f"{cache_prefix}-blender-{blender}",
            }
            for label, runner, session, cache_prefix, blender in targets
        ]
    }


def write_github_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path is None:
        fail("GITHUB_OUTPUT is not set")
    with Path(output_path).open("a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")


def fail(message: str) -> NoReturn:
    sys.stderr.write(f"{message}\n")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
