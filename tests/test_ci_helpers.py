from pathlib import Path

import pytest

from tests.ci import install_blender, put_clipboard_image


@pytest.mark.parametrize(
    ("version", "expected"),
    [("4.2.21", "Blender4.2"), ("4.5.10", "Blender4.5"), ("5.1.2", "Blender5.1")],
)
def test_release_series(version: str, expected: str) -> None:
    assert install_blender.release_series(version) == expected


@pytest.mark.parametrize(
    ("version", "system", "arch", "expected"),
    [
        ("4.2.21", "Linux", "X64", "blender-4.2.21-linux-x64.tar.xz"),
        ("4.5.10", "Windows", "X64", "blender-4.5.10-windows-x64.zip"),
        ("5.1.2", "Windows", "ARM64", "blender-5.1.2-windows-arm64.zip"),
        ("5.1.2", "macOS", "ARM64", "blender-5.1.2-macos-arm64.dmg"),
        ("4.2.21", "macOS", "X64", "blender-4.2.21-macos-x64.dmg"),
    ],
)
def test_blender_asset(version: str, system: str, arch: str, expected: str) -> None:
    assert install_blender.blender_asset(version, system, arch) == expected


def test_blender_asset_rejects_unsupported_platform() -> None:
    with pytest.raises(RuntimeError, match="unsupported Blender platform"):
        install_blender.blender_asset("5.1.2", "Linux", "ARM64")


@pytest.mark.parametrize(
    ("system", "expected"),
    [
        ("Linux", Path("root/blender")),
        ("Windows", Path("root/blender.exe")),
        ("macOS", Path("root/Blender.app/Contents/MacOS/Blender")),
    ],
)
def test_blender_binary(system: str, expected: Path) -> None:
    assert install_blender.blender_binary(Path("root"), system) == expected


def test_install_root_uses_github_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))

    root = install_blender.install_root("5.1.2", "macOS", "ARM64")

    assert root == tmp_path / ".cache" / "blender" / "5.1.2-macOS-ARM64"


@pytest.mark.parametrize(
    ("input_arch", "expected"),
    [("AMD64", "X64"), ("x86_64", "X64"), ("aarch64", "ARM64"), ("arm64", "ARM64")],
)
def test_runner_arch_aliases(
    monkeypatch: pytest.MonkeyPatch, input_arch: str, expected: str
) -> None:
    monkeypatch.setenv("RUNNER_ARCH", input_arch)

    assert install_blender.runner_arch() == expected


def test_runner_os_aliases_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNNER_OS", "Darwin")

    assert install_blender.runner_os() == "macOS"


def test_write_github_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / "github-env"
    blender_path = tmp_path / "blender"
    monkeypatch.setenv("GITHUB_ENV", str(env_file))

    install_blender.write_github_value("GITHUB_ENV", "BLENDER_BIN", str(blender_path))

    assert env_file.read_text(encoding="utf-8") == f"BLENDER_BIN={blender_path}\n"


def test_clipboard_image_is_png() -> None:
    assert put_clipboard_image.PNG_BYTES.startswith(b"\x89PNG\r\n\x1a\n")
