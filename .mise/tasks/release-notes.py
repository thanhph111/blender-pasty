#!/usr/bin/env -S uv run -s --no-sync

# [MISE] description="Print release notes from CHANGELOG.md"
# [USAGE] arg "<version>" help="Version to print, with or without a leading v"

from __future__ import annotations

import argparse
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[2] / "CHANGELOG.md"


def release_notes(markdown: str, version: str) -> str:
    version = version.removeprefix("v")
    target_heading = f"## [{version}]"
    section: list[str] = []
    in_section = False

    for line in markdown.splitlines():
        if line.startswith("## "):
            if in_section:
                break
            in_section = line == target_heading or line.startswith(f"{target_heading} - ")
            continue
        if in_section:
            section.append(line)

    notes = "\n".join(section).strip()
    if not in_section:
        msg = f"missing CHANGELOG.md section for {version}"
        raise RuntimeError(msg)
    if not notes:
        msg = f"empty CHANGELOG.md section for {version}"
        raise RuntimeError(msg)

    return f"{notes}\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="release-notes", description="Print release notes from CHANGELOG.md"
    )
    parser.add_argument("version", help="Version to print, with or without a leading v")
    args = parser.parse_args()

    print(release_notes(CHANGELOG.read_text(encoding="utf-8"), args.version), end="")


if __name__ == "__main__":
    main()
