from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse

if TYPE_CHECKING:
    from collections.abc import Callable

TIMEOUT_SECONDS = 5
XCLIP_SEED_LOOPS = "8"


def main() -> None:
    parser = argparse.ArgumentParser(prog="clipboard_os")
    subparsers = parser.add_subparsers(dest="command", required=True)

    files_commands = ("seed-files", "expect-files")
    for command in files_commands:
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("paths", nargs="+")

    png_commands = ("seed-png",)
    for command in png_commands:
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("path")

    subparsers.add_parser("expect-image")
    subparsers.add_parser("clear")

    args = parser.parse_args()

    if args.command == "seed-files":
        seed_files([Path(path).resolve(strict=False) for path in args.paths])
    elif args.command == "expect-files":
        expect_files([Path(path).resolve(strict=False) for path in args.paths])
    elif args.command == "seed-png":
        seed_png(Path(args.path).resolve(strict=False))
    elif args.command == "expect-image":
        expect_image()
    elif args.command == "clear":
        clear_clipboard()


def seed_files(paths: list[Path]) -> None:
    if sys.platform == "darwin":
        # NSURL pasteboard objects can collapse to one item after this short-lived
        # helper exits. The old file-list type materializes durable file URL items.
        run_macos_script(
            (
                'ObjC.import("AppKit");'
                "const paths = __PATHS__;"
                "const fileList = $.NSMutableArray.arrayWithCapacity(paths.length);"
                "for (const path of paths) {"
                "  fileList.addObject(path);"
                "}"
                "const pasteboard = $.NSPasteboard.generalPasteboard;"
                "/* JXA runs this AppKit method when read; clearContents() throws. */"
                "pasteboard.clearContents;"
                "pasteboard.declareTypesOwner("
                '$.NSArray.arrayWithObject("NSFilenamesPboardType"), null'
                ");"
                'if (!pasteboard.setPropertyListForType(fileList, "NSFilenamesPboardType")) {'
                '  throw new Error("could not write file list to NSPasteboard");'
                "}"
                "paths.length;"
            ).replace("__PATHS__", json.dumps([str(path) for path in paths]))
        )
        return

    if sys.platform == "win32":
        run_windows_clipboard_script(
            """
            Add-Type -AssemblyName System.Windows.Forms
            $pathsJson = [Text.Encoding]::UTF8.GetString(
              [Convert]::FromBase64String('__PATHS_JSON_BASE64__')
            )
            $paths = ConvertFrom-Json $pathsJson
            $files = New-Object System.Collections.Specialized.StringCollection
            foreach ($path in $paths) {
              [void]$files.Add([string](Resolve-Path -LiteralPath $path))
            }
            $data = New-Object System.Windows.Forms.DataObject
            $data.SetFileDropList($files)
            Invoke-Clipboard {
              [System.Windows.Forms.Clipboard]::SetDataObject($data, $true, 20, 100)
            }
            """.replace(
                "__PATHS_JSON_BASE64__",
                powershell_base64_text(json.dumps([str(path) for path in paths])),
            )
        )
        return

    text = "".join(f"{path.as_uri()}\n" for path in paths).encode()
    if linux_wayland_available():
        run(["wl-copy", "--type", "text/uri-list"], stdin=text)
        return
    if linux_x11_available():
        # xclip serves X11 clipboard requests from a live owner process. A single
        # seeded scenario may be read by the OS preflight, Blender's target check,
        # and Blender's actual data read, so allow several reads while still
        # letting clear_clipboard stop the owner at the end.
        run(
            [
                "xclip",
                "-selection",
                "clipboard",
                "-target",
                "text/uri-list",
                "-loops",
                XCLIP_SEED_LOOPS,
            ],
            stdin=text,
        )
        return
    msg = "No supported Linux clipboard command found for file URLs"
    raise RuntimeError(msg)


def expect_files(expected_paths: list[Path]) -> None:
    expected = [path.resolve(strict=False) for path in expected_paths]

    def current_paths_match() -> bool:
        return read_files() == expected

    if wait_for(current_paths_match):
        return

    msg = f"clipboard files did not match: expected {expected}, got {read_files()}"
    raise RuntimeError(msg)


def read_files() -> list[Path]:
    if sys.platform == "darwin":
        output = run_macos_script(
            """
            ObjC.import("AppKit");
            const pasteboard = $.NSPasteboard.generalPasteboard;
            const classes = $.NSArray.arrayWithObject($.NSURL);
            const options = $.NSDictionary.dictionaryWithObjectForKey(
              true,
              $.NSPasteboardURLReadingFileURLsOnlyKey
            );
            const urls = pasteboard.readObjectsForClassesOptions(classes, options);
            const paths = [];
            const legacyFilePaths = [];
            if (urls) {
              for (let index = 0; index < urls.count; index++) {
                const url = urls.objectAtIndex(index);
                if (url.isFileURL) {
                  paths.push(ObjC.unwrap(url.path));
                }
              }
            }
            const legacyPaths = pasteboard.propertyListForType("NSFilenamesPboardType");
            if (legacyPaths) {
              // Some AppKit reads return fewer modern URLs than this durable file list.
              for (let index = 0; index < legacyPaths.count; index++) {
                legacyFilePaths.push(ObjC.unwrap(legacyPaths.objectAtIndex(index)));
              }
            }
            JSON.stringify(legacyFilePaths.length > paths.length ? legacyFilePaths : paths);
            """
        )
        return paths_from_json(output)

    if sys.platform == "win32":
        output = run_windows_clipboard_script(
            """
            Add-Type -AssemblyName System.Windows.Forms
            $paths = @()
            if ([System.Windows.Forms.Clipboard]::ContainsFileDropList()) {
              foreach ($path in [System.Windows.Forms.Clipboard]::GetFileDropList()) {
                $paths += [string]$path
              }
            }
            ConvertTo-Json -Compress @($paths)
            """
        )
        return paths_from_json(output)

    if linux_wayland_available():
        return paths_from_uri_list(run_text(["wl-paste", "--type", "text/uri-list"]))
    if linux_x11_available():
        return paths_from_uri_list(
            run_text(["xclip", "-selection", "clipboard", "-target", "text/uri-list", "-out"])
        )
    return []


def seed_png(path: Path) -> None:
    if sys.platform == "darwin":
        run_macos_script(
            """
            ObjC.import("AppKit");
            const data = $.NSData.dataWithContentsOfFile(__PATH__);
            const image = $.NSImage.alloc.initWithContentsOfFile(__PATH__);
            if (!data || !image) {
              throw new Error("could not read PNG fixture");
            }
            const tiff = image.TIFFRepresentation;
            const types = $.NSMutableArray.array;
            types.addObject($.NSPasteboardTypePNG);
            if (tiff) {
              types.addObject($.NSPasteboardTypeTIFF);
            }
            const pasteboard = $.NSPasteboard.generalPasteboard;
            // JXA runs this AppKit method when read; clearContents() throws.
            pasteboard.clearContents;
            pasteboard.declareTypesOwner(types, null);
            if (!pasteboard.setDataForType(data, $.NSPasteboardTypePNG)) {
              throw new Error("could not write PNG to NSPasteboard");
            }
            if (tiff && !pasteboard.setDataForType(tiff, $.NSPasteboardTypeTIFF)) {
              throw new Error("could not write TIFF to NSPasteboard");
            }
            """.replace("__PATH__", json.dumps(str(path)))
        )
        return

    if sys.platform == "win32":
        run_windows_clipboard_script(
            """
            Add-Type -AssemblyName System.Windows.Forms
            Add-Type -AssemblyName System.Drawing
            $path = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__PATH_BASE64__'))
            $image = [System.Drawing.Image]::FromFile((Resolve-Path -LiteralPath $path))
            try {
              $data = New-Object System.Windows.Forms.DataObject
              $data.SetImage($image)
              Invoke-Clipboard {
                [System.Windows.Forms.Clipboard]::SetDataObject($data, $true, 20, 100)
              }
            }
            finally {
              $image.Dispose()
            }
            """.replace("__PATH_BASE64__", powershell_base64_text(str(path)))
        )
        return

    png = path.read_bytes()
    if linux_wayland_available():
        run(["wl-copy", "--type", "image/png"], stdin=png)
        return
    if linux_x11_available():
        # See seed_files: the image scenario also has more than one clipboard read
        # before Blender reaches the fallback that consumes the PNG bytes.
        run(
            [
                "xclip",
                "-selection",
                "clipboard",
                "-target",
                "image/png",
                "-loops",
                XCLIP_SEED_LOOPS,
            ],
            stdin=png,
        )
        return
    msg = "No supported Linux clipboard command found for PNG data"
    raise RuntimeError(msg)


def expect_image() -> None:
    if wait_for(has_image):
        return
    msg = "clipboard does not contain an image"
    raise RuntimeError(msg)


def has_image() -> bool:
    if sys.platform == "darwin":
        return (
            run_macos_script(
                """
                ObjC.import("AppKit");
                const pasteboard = $.NSPasteboard.generalPasteboard;
                const types = $.NSMutableArray.array;
                types.addObject($.NSPasteboardTypePNG);
                types.addObject($.NSPasteboardTypeTIFF);
                pasteboard.availableTypeFromArray(types) ? "1" : "0";
                """
            ).strip()
            == "1"
        )

    if sys.platform == "win32":
        return (
            run_windows_clipboard_script(
                """
                Add-Type -AssemblyName System.Windows.Forms
                if ([System.Windows.Forms.Clipboard]::ContainsImage()) { "1" } else { "0" }
                """
            ).strip()
            == "1"
        )

    if linux_wayland_available():
        return command_lists_image(["wl-paste", "--list-types"])
    if linux_x11_available():
        return command_lists_image(
            ["xclip", "-selection", "clipboard", "-target", "TARGETS", "-out"]
        )
    return False


def command_lists_image(command: list[str]) -> bool:
    try:
        return "image/png" in run_text(command).split()
    except RuntimeError:
        return False


def clear_clipboard() -> None:
    if sys.platform == "darwin":
        run_macos_script(
            """
            ObjC.import("AppKit");
            // JXA runs this AppKit method when read; clearContents() throws.
            $.NSPasteboard.generalPasteboard.clearContents;
            """
        )
        return

    if sys.platform == "win32":
        run_windows_clipboard_script(
            """
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.Clipboard]::Clear()
            """
        )
        return

    if linux_wayland_available():
        # wl-copy --clear can return non-zero when the new headless compositor has
        # no clipboard owner yet. That is already a clear state for this check.
        run(["wl-copy", "--clear"], check=False)
        return
    if linux_x11_available():
        run(["xclip", "-selection", "clipboard"], stdin=b"")
        stop_xclip_owners()


def stop_xclip_owners() -> None:
    # xclip owns the clipboard by keeping a process alive. That is fine on a
    # desktop, but automated X11 checks need it gone so the test display can exit.
    pkill = shutil.which("pkill")
    if pkill is None:
        return
    subprocess.run(  # noqa: S603
        [pkill, "-x", "xclip"],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=TIMEOUT_SECONDS,
    )


def paths_from_json(output: str) -> list[Path]:
    if not output.strip():
        return []
    values = json.loads(output)
    if isinstance(values, str):
        values = [values]
    return [Path(value).resolve(strict=False) for value in values]


def paths_from_uri_list(text: str) -> list[Path]:
    paths = []
    for line in text.splitlines():
        value = line.strip()
        if not value or value.startswith("#") or value in {"copy", "cut"}:
            continue
        parsed = urlparse(value)
        if parsed.scheme != "file":
            continue
        paths.append(Path(unquote(parsed.path)).resolve(strict=False))
    return paths


def wait_for(predicate: Callable[[], bool]) -> bool:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return predicate()


def linux_wayland_available() -> bool:
    return (
        bool(os.environ.get("WAYLAND_DISPLAY"))
        and shutil.which("wl-copy") is not None
        and shutil.which("wl-paste") is not None
    )


def linux_x11_available() -> bool:
    return bool(os.environ.get("DISPLAY")) and shutil.which("xclip") is not None


def run_macos_script(script: str) -> str:
    return run_text(["/usr/bin/osascript", "-l", "JavaScript", "-e", script])


def powershell_base64_text(text: str) -> str:
    # Passing generated data as base64 keeps PowerShell parsing independent from
    # paths that contain quotes, whitespace, or here-string terminator rules.
    return base64.b64encode(text.encode()).decode("ascii")


def run_windows_clipboard_script(script: str) -> str:
    retry = """
    function Invoke-Clipboard([scriptblock]$Operation) {
      for ($attempt = 1; $attempt -le 20; $attempt++) {
        try {
          return & $Operation
        }
        catch {
          if ($attempt -eq 20) {
            throw
          }
          Start-Sleep -Milliseconds 100
        }
      }
    }
    """
    return run_text(
        [
            "powershell.exe",
            "-NoProfile",
            "-Sta",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "$ErrorActionPreference = 'Stop'; " + retry + script,
        ]
    )


def run_text(command: list[str]) -> str:
    result = subprocess.run(  # noqa: S603
        command,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        command_text = " ".join(command)
        output = "\n".join(
            part
            for part in (
                f"stdout:\n{result.stdout.strip()}" if result.stdout.strip() else "",
                f"stderr:\n{result.stderr.strip()}" if result.stderr.strip() else "",
            )
            if part
        )
        msg = f"Command failed: {command_text}"
        if output:
            msg = f"{msg}\n{output}"
        raise RuntimeError(msg)
    return result.stdout


def run(command: list[str], *, stdin: bytes | None = None, check: bool = True) -> None:
    if stdin is None:
        subprocess.run(  # noqa: S603
            command,
            check=check,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=TIMEOUT_SECONDS,
        )
        return

    subprocess.run(  # noqa: S603
        command,
        check=check,
        input=stdin,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=TIMEOUT_SECONDS,
    )


if __name__ == "__main__":
    main()
