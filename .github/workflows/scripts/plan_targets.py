#!/usr/bin/env python3

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan automated check targets.")
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
        targets = [
            ("Linux", "ubuntu-24.04", "linux", "4.2"),
            ("Linux", "ubuntu-24.04", "linux", "5.1"),
        ]
    else:
        targets = [
            (label, runner, cache_prefix, blender)
            for label, runner, cache_prefix in (
                ("Linux", "ubuntu-24.04", "linux"),
                ("Windows", "windows-2025", "windows"),
                ("macOS", "macos-15", "macos"),
            )
            for blender in ("4.2", "4.5", "5.1")
        ]

    return {
        "include": [
            {
                "label": f"{label}, Blender {blender}",
                "runner": runner,
                "blender": blender,
                "cache_key": f"{cache_prefix}-blender-{blender}",
            }
            for label, runner, cache_prefix, blender in targets
        ]
    }


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
                # checks and headless checks.
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
        sys.stdout.write(f"{name}={value}\n")
        return
    with Path(output_path).open("a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")


if __name__ == "__main__":
    main()
