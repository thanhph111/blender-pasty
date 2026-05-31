import argparse
import os
import platform
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    args = parser.parse_args()

    version = args.version
    system = runner_os()
    arch = runner_arch()
    asset = blender_asset(version, system, arch)
    url = f"https://download.blender.org/release/{release_series(version)}/{asset}"
    root = install_root(version, system, arch)

    blender_bin = blender_binary(root, system)
    if not blender_bin.exists():
        root.mkdir(parents=True, exist_ok=True)
        archive = root / asset
        download(url, archive)
        extract(archive, root, system)
        archive.unlink(missing_ok=True)

    blender_bin = blender_binary(root, system)
    if not blender_bin.exists():
        msg = f"Blender executable was not found after installing {version}"
        raise RuntimeError(msg)

    if system != "Windows":
        blender_bin.chmod(0o755)

    write_github_value("GITHUB_OUTPUT", "blender-bin", str(blender_bin))
    write_github_value("GITHUB_ENV", "BLENDER_BIN", str(blender_bin))
    print(blender_bin)


def runner_os() -> str:
    system = os.environ.get("RUNNER_OS") or platform.system()
    aliases = {"Darwin": "macOS"}
    return aliases.get(system, system)


def runner_arch() -> str:
    arch = os.environ.get("RUNNER_ARCH") or platform.machine()
    aliases = {"AMD64": "X64", "arm64": "ARM64", "aarch64": "ARM64", "x86_64": "X64"}
    return aliases.get(arch, arch)


def release_series(version: str) -> str:
    major, minor, *_ = version.split(".")
    return f"Blender{major}.{minor}"


def blender_asset(version: str, system: str, arch: str) -> str:
    match (system, arch):
        case ("Linux", "X64"):
            suffix = "linux-x64.tar.xz"
        case ("Windows", "X64"):
            suffix = "windows-x64.zip"
        case ("Windows", "ARM64"):
            suffix = "windows-arm64.zip"
        case ("macOS", "ARM64"):
            suffix = "macos-arm64.dmg"
        case ("macOS", "X64"):
            suffix = "macos-x64.dmg"
        case _:
            msg = f"unsupported Blender platform: {system} {arch}"
            raise RuntimeError(msg)

    return f"blender-{version}-{suffix}"


def install_root(version: str, system: str, arch: str) -> Path:
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", Path.cwd()))
    return workspace / ".cache" / "blender" / f"{version}-{system}-{arch}"


def blender_binary(root: Path, system: str) -> Path:
    if system == "macOS":
        return root / "Blender.app" / "Contents" / "MacOS" / "Blender"
    if system == "Windows":
        return root / "blender.exe"
    return root / "blender"


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
        top_level = tar.getmembers()[0].name.split("/")[0]
        tar.extractall(root)

    extracted = root / top_level
    for child in extracted.iterdir():
        shutil.move(str(child), root)
    extracted.rmdir()


def extract_windows(archive: Path, root: Path) -> None:
    with zipfile.ZipFile(archive) as zip_file:
        zip_file.extractall(root)

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
    subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(root / "Blender.app")], check=False)


def write_github_value(env_name: str, key: str, value: str) -> None:
    path = os.environ.get(env_name)
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as file:
        file.write(f"{key}={value}\n")


if __name__ == "__main__":
    main()
