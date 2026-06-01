#!/usr/bin/env -S uv run -s --no-sync

# [MISE] description="Run checks"
# [USAGE] arg "[target]" help="Check target" {
# [USAGE]   choices "repo" "package"
# [USAGE]   default "repo"
# [USAGE] }

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_REPO_ID = "pasty_package_test"
PACKAGE_MODULE = f"bl_ext.{PACKAGE_REPO_ID}.pasty"


def main() -> None:
    parser = argparse.ArgumentParser(prog="test", description="Run checks")
    parser.add_argument("target", nargs="?", choices=("repo", "package"), default="repo")
    args = parser.parse_args()

    if args.target == "repo":
        test_repo()
    elif args.target == "package":
        test_package()


def test_repo() -> None:
    run(["mise", "run", "validate"])
    run(["uv", "run", "--no-sync", "python", "checks/smoke_repo.py"])


def test_package() -> None:
    run(["mise", "run", "build"])
    package = latest_package(ROOT / "dist")
    if not package.is_file():
        msg = f"package not found: {package}"
        raise RuntimeError(msg)

    blender_bin = os.environ.get("BLENDER_BIN") or shutil.which("blender")
    if not blender_bin:
        msg = "Blender not found. Set BLENDER_BIN or put blender on PATH."
        raise RuntimeError(msg)

    with TemporaryDirectory(prefix="pasty-package-") as temp_dir:
        temp_root = Path(temp_dir)
        env = package_test_environment(temp_root)
        repo_dir = temp_root / "extensions" / PACKAGE_REPO_ID
        repo_dir.mkdir(parents=True)

        run_blender(
            blender_bin,
            env,
            "--command",
            "extension",
            "repo-add",
            PACKAGE_REPO_ID,
            "--name",
            "Pasty Package Test",
            "--directory",
            str(repo_dir),
            "--clear-all",
        )
        run_blender(
            blender_bin,
            env,
            "--command",
            "extension",
            "install-file",
            "--repo",
            PACKAGE_REPO_ID,
            "--enable",
            str(package),
        )
        run_blender(blender_bin, env, "--command", "extension", "validate", str(package))
        run_blender(
            blender_bin,
            env | {"PASTY_EXTENSION_MODULE": PACKAGE_MODULE},
            "--background",
            "--python-exit-code",
            "1",
            "--python",
            str(ROOT / "checks" / "smoke_package.py"),
        )


def latest_package(dist_dir: Path) -> Path:
    packages = sorted(
        dist_dir.glob("pasty-*.zip"), key=lambda path: (path.stat().st_mtime_ns, path.name)
    )
    if not packages:
        msg = f"no package found in {dist_dir}"
        raise RuntimeError(msg)
    return packages[-1]


def package_test_environment(temp_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["BLENDER_USER_CONFIG"] = str(temp_root / "config")
    env["BLENDER_USER_EXTENSIONS"] = str(temp_root / "extensions")
    env["BLENDER_USER_SCRIPTS"] = str(temp_root / "scripts")
    for key in ("BLENDER_USER_CONFIG", "BLENDER_USER_EXTENSIONS", "BLENDER_USER_SCRIPTS"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    return env


def run_blender(blender_bin: str, env: dict[str, str], *args: str) -> None:
    command = [blender_bin, *args]
    print(" ".join(command))
    try:
        subprocess.run(command, check=True, cwd=ROOT, env=env)
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
