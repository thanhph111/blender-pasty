import ctypes
import shutil
import subprocess
import sys
from collections.abc import Generator, Iterable, Sequence
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import bpy

from .blender_types import OperatorReturn
from .storage import (
    SOURCE_CLIPBOARD_IMAGE,
    SOURCE_COPIED_FILE,
    STORAGE_ORIGINAL_FILE,
    mark_pasted_image,
)

DEFAULT_IMAGE_FILE_EXTENSIONS = frozenset(
    {
        ".bmp",
        ".cin",
        ".dds",
        ".dpx",
        ".exr",
        ".hdr",
        ".j2c",
        ".jp2",
        ".jpeg",
        ".jpg",
        ".pdd",
        ".png",
        ".psb",
        ".psd",
        ".rgb",
        ".rgba",
        ".sgi",
        ".tga",
        ".tif",
        ".tiff",
        ".tx",
        ".webp",
    }
)
CLIPBOARD_COMMAND_TIMEOUT_SECONDS = 2
LINUX_FILE_CLIPBOARD_TYPES = ("x-special/gnome-copied-files", "text/uri-list")
MACOS_FILE_URL_SCRIPT = """
ObjC.import("AppKit");

const pasteboard = $.NSPasteboard.generalPasteboard;
const classes = $.NSArray.arrayWithObject($.NSURL);
const options = $.NSDictionary.dictionaryWithObjectForKey(
  true,
  $.NSPasteboardURLReadingFileURLsOnlyKey
);
const urls = pasteboard.readObjectsForClassesOptions(classes, options);
const paths = [];

if (urls) {
  for (let index = 0; index < urls.count; index++) {
    const url = urls.objectAtIndex(index);
    if (url.isFileURL) {
      paths.push(ObjC.unwrap(url.path));
    }
  }
}

paths.join("\\n");
"""


@dataclass(slots=True)
class PastedImage:
    image: bpy.types.Image
    source_kind: str
    source_path: Path | None = None


@contextmanager
def temporary_image_editor(area: bpy.types.Area) -> Generator[bpy.types.Area, None, None]:
    """Temporarily switch an area to the Image Editor."""

    # Blender's image clipboard operators belong to the Image Editor.
    # Pasty borrows the current area for one operator call, then puts it back.
    former_area_type = area.type
    former_ui_type = getattr(area, "ui_type", None)

    area.type = "IMAGE_EDITOR"
    try:
        yield area
    finally:
        area.type = former_area_type
        if former_ui_type is not None:
            area.ui_type = former_ui_type


def paste_images_from_clipboard(context: bpy.types.Context) -> list[PastedImage]:
    """Paste images from the clipboard into Blender images."""
    # Copied files are the richer source when they exist: they keep names,
    # multiple selections, source paths, and real file formats.
    file_images = paste_image_files_from_clipboard(context)
    if file_images:
        return file_images

    # Clipboard pixels cover screenshots, browsers, and image editors.
    image = paste_image_data_from_clipboard(context)
    if image is not None:
        return [image]

    return []


def image_clipboard_paste_result() -> OperatorReturn | None:
    # Blender raises RuntimeError when the operator's poll check fails.
    # For Pasty, that is just "no clipboard image"; the text-path fallback should still run.
    try:
        return bpy.ops.image.clipboard_paste()
    except RuntimeError:
        return None


def paste_image_data_from_clipboard(context: bpy.types.Context) -> PastedImage | None:
    if context.area is None:
        return None

    keys_before = set(bpy.data.images.keys())
    with temporary_image_editor(context.area):
        result = image_clipboard_paste_result()
    if result != {"FINISHED"}:
        return None

    # The Blender operator returns only a status, not the new image.
    # Compare image keys before and after to find the image it created.
    keys_after = set(bpy.data.images.keys())
    new_keys = keys_after - keys_before
    if not new_keys:
        return None

    image_id = new_keys.pop()
    image = bpy.data.images[image_id]

    mark_pasted_image(image, source_kind=SOURCE_CLIPBOARD_IMAGE)
    return PastedImage(image, SOURCE_CLIPBOARD_IMAGE)


def paste_image_files_from_clipboard(context: bpy.types.Context) -> list[PastedImage]:
    if context.window_manager is None:
        return []

    images = []
    for filepath in image_file_paths_from_clipboard(context.window_manager.clipboard):
        image = load_image_file(filepath)
        if image is not None:
            images.append(PastedImage(image, SOURCE_COPIED_FILE, filepath))

    return images


def image_file_paths_from_clipboard(text: str) -> list[Path]:
    text_paths = image_file_paths_from_clipboard_text(text)

    if sys.platform in {"win32", "darwin"}:
        native_paths = existing_image_file_paths(platform_clipboard_file_paths())
        if native_paths:
            return existing_image_file_paths([*native_paths, *text_paths])

    # File managers often use native copied-file formats that are not exposed as
    # Blender text. Read only those file-list formats here; raw image pixels still
    # belong to bpy.ops.image.clipboard_paste().
    if text_paths:
        return text_paths

    # On Linux, Blender/Wayland usually exposes text/uri-list through the text
    # clipboard already. wl-paste/xclip are optional fallbacks for desktop sessions
    # where Blender gets no useful text.
    return existing_image_file_paths(platform_clipboard_file_paths())


def image_file_paths_from_clipboard_text(text: str) -> list[Path]:
    candidates = []
    for line in text.splitlines():
        path = image_file_path_from_clipboard_line(line)
        if path is not None:
            candidates.append(path)
    return existing_image_file_paths(candidates)


def existing_image_file_paths(candidates: Iterable[Path]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    image_extensions = getattr(bpy.path, "extensions_image", DEFAULT_IMAGE_FILE_EXTENSIONS)
    for path in candidates:
        if path.suffix.lower() not in image_extensions:
            continue
        if not path.is_file() or path in seen:
            continue
        paths.append(path)
        seen.add(path)
    return paths


def image_file_path_from_clipboard_line(line: str) -> Path | None:
    value = line.strip().strip("\"'")
    # Some file managers put an operation marker before the file list.
    if not value or value in {"copy", "cut"} or value.startswith("#"):
        return None

    parsed = urlparse(value)
    is_network_file_url = False
    if parsed.scheme == "file":
        # File URLs are the common cross-platform text form for copied files.
        value = unquote(parsed.path)
        if parsed.netloc and parsed.netloc != "localhost":
            is_network_file_url = True
            value = f"//{parsed.netloc}{value}"
        if sys.platform == "win32" and value.startswith("/") and Path(value[1:]).drive:
            # Windows file URLs look like /C:/path after parsing; pathlib needs C:/path.
            value = value[1:]

    if value.startswith("//") and not is_network_file_url:
        path = Path(bpy.path.abspath(value))
    else:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = Path(bpy.path.abspath(str(path)))
    image_extensions = getattr(bpy.path, "extensions_image", DEFAULT_IMAGE_FILE_EXTENSIONS)
    if path.suffix.lower() not in image_extensions:
        return None
    if not path.is_file():
        return None
    return path


def platform_clipboard_file_paths() -> list[Path]:
    if sys.platform == "win32":
        return windows_clipboard_file_paths()
    if sys.platform == "darwin":
        return macos_clipboard_file_paths()
    if sys.platform.startswith("linux"):
        return linux_clipboard_file_paths()
    return []


def windows_clipboard_file_paths() -> list[Path]:
    # Windows Explorer exposes copied files through CF_HDROP. Blender can read a
    # single image file from that format as pixels, but Pasty needs the original
    # file paths so multiple copied files keep their names and formats.
    cf_hdrop = 15
    windows_library = getattr(ctypes, "WinDLL", None)
    if windows_library is None:
        return []
    user32 = windows_library("user32", use_last_error=True)
    shell32 = windows_library("shell32", use_last_error=True)

    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    shell32.DragQueryFileW.argtypes = [
        wintypes.HANDLE,
        wintypes.UINT,
        wintypes.LPWSTR,
        wintypes.UINT,
    ]
    shell32.DragQueryFileW.restype = wintypes.UINT

    if not user32.IsClipboardFormatAvailable(cf_hdrop):
        return []
    if not user32.OpenClipboard(None):
        return []

    try:
        handle = user32.GetClipboardData(cf_hdrop)
        if not handle:
            return []

        file_count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
        paths = []
        for index in range(file_count):
            character_count = shell32.DragQueryFileW(handle, index, None, 0)
            if character_count == 0:
                continue
            buffer = ctypes.create_unicode_buffer(character_count + 1)
            if shell32.DragQueryFileW(handle, index, buffer, character_count + 1):
                paths.append(Path(buffer.value))
        return paths
    finally:
        user32.CloseClipboard()


def macos_clipboard_file_paths() -> list[Path]:
    osascript = Path("/usr/bin/osascript")
    if not osascript.exists():
        return []
    output = clipboard_command_output(
        [str(osascript), "-l", "JavaScript", "-e", MACOS_FILE_URL_SCRIPT]
    )
    return [Path(line).expanduser() for line in output.splitlines() if line.strip()]


def linux_clipboard_file_paths() -> list[Path]:
    wayland_paths = linux_clipboard_file_paths_with_wl_paste()
    if wayland_paths:
        return wayland_paths
    return linux_clipboard_file_paths_with_xclip()


def linux_clipboard_file_paths_with_wl_paste() -> list[Path]:
    wl_paste = executable_path("wl-paste")
    if wl_paste is None:
        return []

    targets = set(clipboard_command_output([wl_paste, "--list-types"]).split())
    texts = [
        clipboard_command_output([wl_paste, "--no-newline", "--type", clipboard_type])
        for clipboard_type in LINUX_FILE_CLIPBOARD_TYPES
        if clipboard_type in targets
    ]
    return image_file_paths_from_clipboard_text("\n".join(texts))


def linux_clipboard_file_paths_with_xclip() -> list[Path]:
    xclip = executable_path("xclip")
    if xclip is None:
        return []

    targets = set(
        clipboard_command_output(
            [xclip, "-selection", "clipboard", "-target", "TARGETS", "-out"]
        ).split()
    )
    texts = [
        clipboard_command_output(
            [xclip, "-selection", "clipboard", "-target", clipboard_type, "-out"]
        )
        for clipboard_type in LINUX_FILE_CLIPBOARD_TYPES
        if clipboard_type in targets
    ]
    return image_file_paths_from_clipboard_text("\n".join(texts))


def executable_path(name: str) -> str | None:
    path = shutil.which(name)
    if path is None:
        return None
    executable = Path(path)
    if not executable.is_absolute():
        return None
    return str(executable)


def clipboard_command_output(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(  # noqa: S603
            command,
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            text=True,
            timeout=CLIPBOARD_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def load_image_file(filepath: Path) -> bpy.types.Image | None:
    try:
        # Reuse an already-loaded image for the same path instead of making duplicates.
        image = bpy.data.images.load(str(filepath), check_existing=True)
    except RuntimeError:
        return None
    return mark_pasted_image(
        image,
        source_kind=SOURCE_COPIED_FILE,
        source_path=filepath,
        storage_kind=STORAGE_ORIGINAL_FILE,
    )


def paste_failed(operator: bpy.types.Operator) -> OperatorReturn:
    operator.report({"WARNING"}, "No compatible image on the clipboard")
    return {"CANCELLED"}


def copy_failed(operator: bpy.types.Operator) -> OperatorReturn:
    operator.report({"WARNING"}, "No image available to copy")
    return {"CANCELLED"}


def copy_image_to_clipboard(context: bpy.types.Context, image: bpy.types.Image) -> bool:
    if context.area is None:
        return False

    with temporary_image_editor(context.area):
        space = context.area.spaces.active
        previous_image = getattr(space, "image", None)
        space.image = image
        try:
            try:
                return bpy.ops.image.clipboard_copy() == {"FINISHED"}
            except RuntimeError:
                # Copy can fail its poll check on platforms without image clipboard support.
                return False
        finally:
            space.image = previous_image
