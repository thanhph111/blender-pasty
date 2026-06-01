#!/usr/bin/env -S uv run -s --no-sync

# [MISE] description="Blender check helpers"
# [USAGE] cmd install help="Install a Blender build for automated checks" {
# [USAGE]   arg "<version>" help="Blender version or series, such as 4.2 or 4.2.21"
# [USAGE] }
# [USAGE] cmd run help="Run the Blender binary used by automated checks" {
# [USAGE]   arg "[args]..." help="Arguments passed to Blender"
# [USAGE] }

import argparse
import os
import platform
import re
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(prog="blender")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install", help="Install a Blender build for automated checks")
    install.add_argument("version")

    run = subparsers.add_parser("run", help="Run the Blender binary used by automated checks")
    run.add_argument("args", nargs=argparse.REMAINDER)

    args = parser.parse_args()

    if args.command == "install":
        install_blender(args.version)
    elif args.command == "run":
        run_blender(args.args)


def install_blender(version_spec: str) -> None:
    system = runner_os()
    arch = runner_arch()
    version = resolve_version(version_spec, system, arch)
    asset = blender_asset(version, system, arch)
    url = f"https://download.blender.org/release/{release_series(version)}/{asset}"
    root = install_root(version_spec, system, arch)

    # The cache key is the requested series. If a newer patch appears, replace the cached build.
    blender_bin = blender_binary(root, system)
    make_executable(blender_bin, system)
    if blender_bin.exists() and installed_version(blender_bin) != version:
        print(f"cached Blender does not match {version}; reinstalling")
        shutil.rmtree(root)

    cache_updated = False
    if not blender_bin.exists():
        root.mkdir(parents=True, exist_ok=True)
        archive = root / asset
        download(url, archive)
        extract(archive, root, system)
        archive.unlink(missing_ok=True)
        cache_updated = True

    blender_bin = blender_binary(root, system)
    if not blender_bin.exists():
        msg = f"Blender executable was not found after installing {version}"
        raise RuntimeError(msg)

    make_executable(blender_bin, system)
    actual_version = installed_version(blender_bin)
    if actual_version != version:
        msg = f"Blender executable is {actual_version or 'unknown'}, expected {version}"
        raise RuntimeError(msg)

    write_github_value("GITHUB_OUTPUT", "blender-bin", str(blender_bin))
    write_github_value("GITHUB_OUTPUT", "cache_updated", str(cache_updated).lower())
    write_github_value("GITHUB_ENV", "BLENDER_BIN", str(blender_bin))
    print(f"Blender {version}")
    print(blender_bin)


def run_blender(args: list[str]) -> None:
    blender_bin = os.environ.get("BLENDER_BIN")
    if not blender_bin:
        msg = "BLENDER_BIN is not set"
        raise RuntimeError(msg)

    if args[:1] == ["--"]:
        args = args[1:]

    subprocess.run([blender_bin, *args], check=True)


def runner_os() -> str:
    system = os.environ.get("RUNNER_OS") or platform.system()
    aliases = {"Darwin": "macOS"}
    return aliases.get(system, system)


def runner_arch() -> str:
    arch = os.environ.get("RUNNER_ARCH") or platform.machine()
    aliases = {"AMD64": "X64", "arm64": "ARM64", "aarch64": "ARM64", "x86_64": "X64"}
    return aliases.get(arch, arch)


def release_series(version: str) -> str:
    return f"Blender{version_series(version)}"


def version_series(version: str) -> str:
    major, minor, *_ = version.split(".")
    return f"{major}.{minor}"


def resolve_version(version: str, system: str, arch: str) -> str:
    if is_exact_version(version):
        return version
    if not is_version_series(version):
        msg = f"expected Blender version like 4.2 or 4.2.21, got {version}"
        raise RuntimeError(msg)

    suffix = blender_asset_suffix(system, arch)
    # GitHub checks ask for series like 4.2 so they stay on the newest official patch.
    return latest_patch_version(version, suffix)


def is_exact_version(version: str) -> bool:
    return re.fullmatch(r"\d+\.\d+\.\d+", version) is not None


def is_version_series(version: str) -> bool:
    return re.fullmatch(r"\d+\.\d+", version) is not None


def latest_patch_version(series: str, suffix: str) -> str:
    url = f"https://download.blender.org/release/Blender{series}/"
    result = subprocess.run(
        ["curl", "--fail", "--location", "--retry", "3", "--silent", "--show-error", url],
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_latest_patch_version(series, suffix, result.stdout)


def parse_latest_patch_version(series: str, suffix: str, html: str) -> str:
    # Match the platform suffix too; not every Blender series ships every platform.
    pattern = re.compile(rf"blender-({re.escape(series)}\.(\d+))-{re.escape(suffix)}")
    matches = [(int(patch), version) for version, patch in pattern.findall(html)]
    if not matches:
        msg = f"could not find Blender {series} asset for {suffix}"
        raise RuntimeError(msg)

    return max(matches)[1]


def blender_asset(version: str, system: str, arch: str) -> str:
    return f"blender-{version}-{blender_asset_suffix(system, arch)}"


def blender_asset_suffix(system: str, arch: str) -> str:
    match (system, arch):
        case ("Linux", "X64"):
            return "linux-x64.tar.xz"
        case ("Windows", "X64"):
            return "windows-x64.zip"
        case ("Windows", "ARM64"):
            return "windows-arm64.zip"
        case ("macOS", "ARM64"):
            return "macos-arm64.dmg"
        case ("macOS", "X64"):
            return "macos-x64.dmg"
        case _:
            msg = f"unsupported Blender platform: {system} {arch}"
            raise RuntimeError(msg)


def install_root(version: str, system: str, arch: str) -> Path:
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", Path.cwd()))
    # Store by major.minor so cache refresh can replace 4.2.20 with 4.2.21 in place.
    return workspace / ".cache" / "blender" / f"{version_series(version)}-{system}-{arch}"


def blender_binary(root: Path, system: str) -> Path:
    if system == "macOS":
        return root / "Blender.app" / "Contents" / "MacOS" / "Blender"
    if system == "Windows":
        return root / "blender.exe"
    return root / "blender"


def make_executable(blender_bin: Path, system: str) -> None:
    if system != "Windows" and blender_bin.exists():
        blender_bin.chmod(0o755)


def installed_version(blender_bin: Path) -> str | None:
    try:
        result = subprocess.run(
            [str(blender_bin), "--version"], check=True, capture_output=True, text=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    return parse_blender_version(result.stdout)


def parse_blender_version(output: str) -> str | None:
    match = re.search(r"^Blender\s+(\d+\.\d+\.\d+)", output, re.MULTILINE)
    if match is None:
        return None
    return match.group(1)


def download(url: str, archive: Path) -> None:
    print(f"downloading {url}")
    subprocess.run(
        ["curl", "--fail", "--location", "--retry", "3", "--output", str(archive), url], check=True
    )


def extract(archive: Path, root: Path, system: str) -> None:
    if system == "Linux":
        extract_linux(archive, root)
    elif system == "Windows":
        extract_windows(archive, root)
    elif system == "macOS":
        extract_macos(archive, root)
    else:
        msg = f"unsupported platform: {system}"
        raise RuntimeError(msg)


def extract_linux(archive: Path, root: Path) -> None:
    with tarfile.open(archive) as tar:
        # Official Linux archives contain a top-level blender-* folder.
        top_level = tar.getmembers()[0].name.split("/")[0]
        tar.extractall(root)

    extracted = root / top_level
    for child in extracted.iterdir():
        shutil.move(str(child), root)
    extracted.rmdir()


def extract_windows(archive: Path, root: Path) -> None:
    with zipfile.ZipFile(archive) as zip_file:
        zip_file.extractall(root)

    # Windows zip layout has changed before; find blender.exe instead of assuming one folder name.
    candidates = sorted(root.rglob("blender.exe"))
    if not candidates:
        msg = f"could not find blender.exe in {archive}"
        raise RuntimeError(msg)

    app_root = candidates[0].parent
    if app_root != root:
        for child in app_root.iterdir():
            shutil.move(str(child), root)
        app_root.rmdir()


def extract_macos(archive: Path, root: Path) -> None:
    mount = root / "mount"
    mount.mkdir(exist_ok=True)
    # Blender ships macOS builds as DMGs, so GitHub checks mount, copy, then detach.
    subprocess.run(
        ["hdiutil", "attach", str(archive), "-mountpoint", str(mount), "-quiet", "-nobrowse"],
        check=True,
    )
    try:
        app_path = next(mount.glob("*.app"))
        shutil.copytree(app_path, root / "Blender.app", dirs_exist_ok=True)
    finally:
        subprocess.run(["hdiutil", "detach", str(mount), "-quiet"], check=True)
        mount.rmdir()
    # GitHub runners can preserve quarantine metadata from downloaded DMGs.
    subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(root / "Blender.app")], check=False)


def write_github_value(env_name: str, key: str, value: str) -> None:
    path = os.environ.get(env_name)
    if not path:
        return
    # GitHub Actions passes outputs/env through files, not stdout parsing.
    with Path(path).open("a", encoding="utf-8") as file:
        file.write(f"{key}={value}\n")


if __name__ == "__main__":
    main()
