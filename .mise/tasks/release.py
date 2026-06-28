#!/usr/bin/env -S uv run -s --no-sync

# [MISE] description="Release helpers"
# [USAGE] cmd notes help="Print release notes from CHANGELOG.md" {
# [USAGE]   arg "<version>" help="Version to print, with or without a leading v"
# [USAGE] }
# [USAGE] cmd prepare help="Update release version files" {
# [USAGE]   arg "<version>" help="Version to prepare, with or without a leading v"
# [USAGE]   flag "--date <date>" help="Release date in YYYY-MM-DD format"
# [USAGE] }
# [USAGE] cmd ship help="Create and push the signed release tag" {
# [USAGE]   arg "<version>" help="Version to release, with or without a leading v"
# [USAGE]   flag "--dry-run" help="Run release checks without creating or pushing the tag"
# [USAGE]   flag "--no-watch" help="Do not wait for the GitHub release workflow"
# [USAGE] }
# [USAGE] cmd upload help="Start the Blender Extensions upload for an existing tag" {
# [USAGE]   arg "<version>" help="Version to upload, with or without a leading v"
# [USAGE] }

# This task prints release status and runs local git, uv, and gh commands.
# ruff: noqa: S603, S607, T201

from __future__ import annotations

import argparse
import re
import subprocess
import time
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = Path(__file__).resolve().parents[2] / "CHANGELOG.md"
MANIFEST = Path(__file__).resolve().parents[2] / "blender_manifest.toml"
RELEASE_WORKFLOW = "release.yml"


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
    parser = argparse.ArgumentParser(prog="release", description="Release helpers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    notes = subparsers.add_parser("notes", help="Print release notes from CHANGELOG.md")
    notes.add_argument("version", help="Version to print, with or without a leading v")

    prepare = subparsers.add_parser("prepare", help="Update release version files")
    prepare.add_argument("version", help="Version to prepare, with or without a leading v")
    prepare.add_argument("--date", help="Release date in YYYY-MM-DD format")

    ship = subparsers.add_parser("ship", help="Create and push the signed release tag")
    ship.add_argument("version", help="Version to release, with or without a leading v")
    ship.add_argument("--dry-run", action="store_true", help="Run checks without tagging")
    ship.add_argument(
        "--no-watch", action="store_true", help="Do not wait for the release workflow"
    )

    upload = subparsers.add_parser("upload", help="Start the Blender Extensions upload")
    upload.add_argument("version", help="Version to upload, with or without a leading v")

    args = parser.parse_args()
    match args.command:
        case "notes":
            print(release_notes(CHANGELOG.read_text(encoding="utf-8"), args.version), end="")
        case "prepare":
            prepare_release(args.version, release_date=args.date)
        case "ship":
            ship_release(args.version, dry_run=args.dry_run, watch=not args.no_watch)
        case "upload":
            upload_to_blender_extensions(args.version)


def prepare_release(version_arg: str, *, release_date: str | None) -> None:
    version = normalize_version(version_arg)
    resolved_date = normalize_release_date(release_date)
    manifest = prepared_manifest(version)
    changelog = prepared_changelog(version, resolved_date)
    MANIFEST.write_text(manifest, encoding="utf-8")
    CHANGELOG.write_text(changelog, encoding="utf-8")
    print(f"prepared release files for v{version}")


def verify_release(version_arg: str) -> str:
    version = normalize_version(version_arg)
    tag = release_tag(version)
    ensure_clean_tree()
    ensure_head_is_on_remote_main()
    ensure_manifest_version(version)
    release_notes(CHANGELOG.read_text(encoding="utf-8"), version)
    run(["uv", "lock", "--check"])
    ensure_tag_is_new(tag)
    return version


def ship_release(version_arg: str, *, dry_run: bool, watch: bool) -> None:
    version = verify_release(version_arg)
    tag = release_tag(version)
    if dry_run:
        print(f"release ship dry run passed for {tag}")
        return

    run(["git", "tag", "-s", tag, "-m", f"Pasty {version}"])
    run(["git", "push", "origin", tag])
    print(f"pushed {tag}")
    if watch:
        watch_release_workflow(tag)


def upload_to_blender_extensions(version_arg: str) -> None:
    version = normalize_version(version_arg)
    tag = release_tag(version)
    ensure_existing_remote_tag(tag)
    run(
        [
            "gh",
            "workflow",
            "run",
            RELEASE_WORKFLOW,
            "--raw-field",
            f"tag={tag}",
            "--raw-field",
            "upload_blender_extensions=true",
        ]
    )
    print(f"started Blender Extensions upload for {tag}")


def normalize_version(version: str) -> str:
    normalized = version.removeprefix("v")
    if re.fullmatch(r"\d+\.\d+\.\d+", normalized) is None:
        msg = f"expected version like 0.2.0 or v0.2.0, got {version}"
        raise RuntimeError(msg)
    return normalized


def normalize_release_date(value: str | None) -> str:
    if value is None:
        return datetime.now(tz=UTC).astimezone().date().isoformat()

    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        msg = f"expected release date like 2026-06-28, got {value}"
        raise RuntimeError(msg) from error
    return parsed.isoformat()


def release_tag(version: str) -> str:
    return f"v{version}"


def prepared_manifest(version: str) -> str:
    lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith("version = "):
            lines[index] = f'version = "{version}"'
            return "\n".join(lines) + "\n"

    msg = "missing version field in blender_manifest.toml"
    raise RuntimeError(msg)


def prepared_changelog(version: str, release_date: str) -> str:
    changelog = CHANGELOG.read_text(encoding="utf-8")
    if changelog_has_version(changelog, version):
        msg = f"CHANGELOG.md already has a section for {version}"
        raise RuntimeError(msg)

    lines = changelog.splitlines()
    try:
        unreleased_start = lines.index("## [Unreleased]")
    except ValueError as error:
        msg = "missing CHANGELOG.md Unreleased section"
        raise RuntimeError(msg) from error

    unreleased_end = next(
        (
            index
            for index, line in enumerate(lines[unreleased_start + 1 :], start=unreleased_start + 1)
            if line.startswith("## ")
        ),
        len(lines),
    )
    notes = "\n".join(lines[unreleased_start + 1 : unreleased_end]).strip()
    if not notes:
        msg = "CHANGELOG.md Unreleased section is empty"
        raise RuntimeError(msg)

    updated = [
        *lines[: unreleased_start + 1],
        "",
        f"## [{version}] - {release_date}",
        "",
        *notes.splitlines(),
        "",
        *lines[unreleased_end:],
    ]
    return "\n".join(updated).rstrip() + "\n"


def changelog_has_version(changelog: str, version: str) -> bool:
    target_heading = f"## [{version}]"
    return any(
        line == target_heading or line.startswith(f"{target_heading} - ")
        for line in changelog.splitlines()
    )


def ensure_manifest_version(version: str) -> None:
    with MANIFEST.open("rb") as manifest_file:
        manifest = tomllib.load(manifest_file)
    manifest_version = str(manifest["version"])
    if manifest_version == version:
        return
    msg = f"blender_manifest.toml version is {manifest_version}, expected {version}"
    raise RuntimeError(msg)


def ensure_clean_tree() -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, check=True, capture_output=True, text=True
    )
    if not result.stdout.strip():
        return
    msg = "working tree is not clean"
    raise RuntimeError(msg)


def ensure_head_is_on_remote_main() -> None:
    subprocess.run(
        ["git", "fetch", "--quiet", "origin", "+refs/heads/main:refs/remotes/origin/main"],
        cwd=ROOT,
        check=True,
    )
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", "HEAD", "refs/remotes/origin/main"],
        cwd=ROOT,
        check=False,
    )
    if result.returncode == 0:
        return
    msg = "release commit is not on origin/main; merge or push it to main before tagging"
    raise RuntimeError(msg)


def ensure_tag_is_new(tag: str) -> None:
    local = subprocess.run(
        ["git", "rev-parse", "--quiet", "--verify", f"refs/tags/{tag}"], cwd=ROOT, check=False
    )
    if local.returncode == 0:
        msg = f"local tag already exists: {tag}"
        raise RuntimeError(msg)

    remote = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--tags", "origin", f"refs/tags/{tag}"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if remote.returncode == 0:
        msg = f"remote tag already exists: {tag}"
        raise RuntimeError(msg)


def ensure_existing_remote_tag(tag: str) -> None:
    remote = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--tags", "origin", f"refs/tags/{tag}"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if remote.returncode == 0:
        return
    msg = f"remote tag does not exist: {tag}"
    raise RuntimeError(msg)


def watch_release_workflow(tag: str) -> None:
    run_id = release_run_id(tag)
    run(["gh", "run", "watch", run_id, "--compact", "--exit-status"])


def release_run_id(tag: str) -> str:
    for _attempt in range(30):
        result = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "--workflow",
                RELEASE_WORKFLOW,
                "--branch",
                tag,
                "--event",
                "push",
                "--limit",
                "1",
                "--json",
                "databaseId",
                "--jq",
                ".[0].databaseId // empty",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        run_id = result.stdout.strip()
        if run_id:
            return run_id
        time.sleep(2)
    msg = f"could not find release workflow run for {tag}"
    raise RuntimeError(msg)


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
