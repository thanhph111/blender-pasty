#!/usr/bin/env -S uv run -s --no-sync

# [MISE] description="Development helpers for Blender"
# [USAGE] cmd paths help="Print Blender development paths"
# [USAGE] cmd link help="Link this repo into the Blender development extension folder"
# [USAGE] cmd repo-add help="Add the development extension folder to Blender"
# [USAGE] cmd install help="Build and install the packaged extension into Blender" {
# [USAGE]   flag "--repo <repo>" help="Blender extension repository id"
# [USAGE] }
# [USAGE] cmd debug help="Launch Blender with debugpy listening" {
# [USAGE]   flag "--host <host>" default="127.0.0.1" help="Debug host"
# [USAGE]   flag "--port <port>" default="5678" help="Debug port"
# [USAGE]   flag "--wait" help="Wait for debugger attach on launch"
# [USAGE]   flag "--blender <path>" help="Path to the Blender executable"
# [USAGE] }

# This task launches local Blender/mise commands and prints setup paths.
# ruff: noqa: S603, T201

import argparse
import os
import platform
import shutil
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "blender_manifest.toml"
REPO_ID = "pasty-dev"


def main() -> None:
    parser = argparse.ArgumentParser(prog="dev", description="Development helpers for Blender")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("paths", help="Print dev paths")
    subparsers.add_parser("link", help="Link this repo into the dev extension folder")
    subparsers.add_parser("repo-add", help="Add the dev extension folder to Blender")

    install = subparsers.add_parser("install", help="Build and install the packaged extension")
    install.add_argument("--repo", default=REPO_ID, help="Blender extension repository id")

    debug = subparsers.add_parser("debug", help="Launch Blender with debugpy listening")
    debug.add_argument("--host", default="127.0.0.1", help="Debug host")
    debug.add_argument("--port", type=int, default=5678, help="Debug port")
    debug.add_argument("--wait", action="store_true", help="Wait for debugger attach on launch")
    debug.add_argument("--blender", help="Path to the Blender executable")

    args = parser.parse_args()
    match args.command:
        case "paths":
            print_paths()
        case "link":
            link_repo()
        case "repo-add":
            repo_add()
        case "install":
            install_package(args.repo)
        case "debug":
            launch_debug(args.host, args.port, wait=args.wait, blender_arg=args.blender)


def extension_id() -> str:
    with MANIFEST.open("rb") as manifest_file:
        manifest = tomllib.load(manifest_file)
    return str(manifest["id"])


def dev_extensions_dir() -> Path:
    configured = os.environ.get("PASTY_DEV_EXTENSIONS_DIR")
    if configured:
        return Path(configured).expanduser().resolve()

    # Keep the live dev repository outside Blender's own install folders.
    # This works on all OSes and avoids admin/root permissions.
    if platform.system() == "Windows":
        return Path.home() / "Documents" / "Blender" / "dev-extensions"

    return Path.home() / "Blender" / "dev-extensions"


def dev_link_path() -> Path:
    return dev_extensions_dir() / extension_id()


def print_paths() -> None:
    print(f"repo:          {ROOT}")
    print(f"dev repo dir:  {dev_extensions_dir()}")
    print(f"dev link:      {dev_link_path()}")
    print(f"repo id:       {REPO_ID}")


def link_repo() -> None:
    link_parent = dev_extensions_dir()
    link_path = dev_link_path()
    link_parent.mkdir(parents=True, exist_ok=True)

    # Only replace our own symlink. A real folder here may contain user work.
    if link_path.is_symlink():
        if link_path.resolve() == ROOT:
            print(f"already linked: {link_path} -> {ROOT}")
            return
        link_path.unlink()
    elif link_path.exists():
        msg = f"{link_path} already exists and is not a symlink"
        raise RuntimeError(msg)

    try:
        link_path.symlink_to(ROOT, target_is_directory=True)
    except OSError as error:
        if platform.system() == "Windows":
            msg = (
                "could not create the Windows symlink. Enable Developer Mode or run the shell "
                "as administrator, then rerun `mise run dev link`."
            )
            raise RuntimeError(msg) from error
        raise

    print(f"linked: {link_path} -> {ROOT}")


def repo_add() -> None:
    # Blender repositories point at the parent folder. The add-on folder inside it is the symlink.
    link_repo()
    run(
        [
            "mise",
            "run",
            "extension",
            "--",
            "repo-add",
            REPO_ID,
            "--name",
            "Pasty Dev",
            "--directory",
            str(dev_extensions_dir()),
        ]
    )


def install_package(repo: str) -> None:
    run(["mise", "run", "build"])
    zip_path = built_zip_path()
    run(["mise", "run", "extension", "--", "install-file", "-r", repo, "-e", str(zip_path)])


def built_zip_path() -> Path:
    zip_paths = sorted((ROOT / "dist").glob("pasty-*.zip"))
    if not zip_paths:
        msg = "no built extension zip found under dist"
        raise RuntimeError(msg)
    return zip_paths[-1]


def launch_debug(host: str, port: int, *, wait: bool, blender_arg: str | None) -> None:
    blender_path = blender_arg or os.environ.get("BLENDER_BIN") or find_blender()
    if blender_path is None:
        msg = "could not find Blender. Set BLENDER_BIN or pass --blender"
        raise RuntimeError(msg)

    debugpy_path = ensure_debugpy(blender_path)

    env = os.environ.copy()

    # Use --python-expr so debugging works without modifying the add-on package.
    expr = (
        "import sys; "
        f"sys.path.insert(0, {str(debugpy_path)!r}); "
        "import debugpy; "
        f"debugpy.listen(({host!r}, {port})); "
        f"print('debugpy listening on {host}:{port}')"
    )
    if wait:
        expr += "; debugpy.wait_for_client(); print('debugger attached')"

    run([blender_path, "--python-expr", expr], env=env)


def ensure_debugpy(blender_path: str) -> Path:
    blender_python, python_tag = blender_python_info(blender_path)
    target = ROOT / ".cache" / "blender-debugpy" / python_tag
    if (target / "debugpy" / "__init__.py").exists():
        return target

    # Install into Blender's Python version, not the repo venv.
    # Blender and local Python can be different minor versions.
    target.mkdir(parents=True, exist_ok=True)
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(blender_python),
            "--target",
            str(target),
            "debugpy",
        ]
    )
    return target


def blender_python_info(blender_path: str) -> tuple[Path, str]:
    # Blender prints startup text too, so emit stable marker lines and parse only those.
    expr = (
        "import sys; "
        "print('PASTY_PYTHON=' + sys.executable); "
        "print('PASTY_PYTHON_TAG=python%d.%d' % sys.version_info[:2])"
    )
    result = subprocess.run(
        [blender_path, "--background", "--factory-startup", "--python-expr", expr],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    python_path = None
    python_tag = None
    for line in result.stdout.splitlines():
        if line.startswith("PASTY_PYTHON="):
            python_path = Path(line.removeprefix("PASTY_PYTHON="))
        elif line.startswith("PASTY_PYTHON_TAG="):
            python_tag = line.removeprefix("PASTY_PYTHON_TAG=")

    if python_path is None or python_tag is None:
        msg = f"could not find Blender's Python executable from {blender_path}"
        raise RuntimeError(msg)

    return python_path, python_tag


def find_blender() -> str | None:
    blender_path = shutil.which("blender")
    if blender_path:
        return blender_path

    # The macOS app bundle does not always put blender on PATH.
    macos_path = Path("/Applications/Blender.app/Contents/MacOS/Blender")
    if macos_path.exists():
        return str(macos_path)

    return None


def run(command: list[str], env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


if __name__ == "__main__":
    main()
