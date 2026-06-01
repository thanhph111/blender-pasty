import sys
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

import bpy

from .blender_types import OperatorReturn

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


def paste_images_from_clipboard(context: bpy.types.Context) -> list[bpy.types.Image]:
    """Paste images from the clipboard into Blender image data-blocks."""
    # Prefer Blender's native raw-image path. Only fall back to text paths if that fails.
    image = paste_image_data_from_clipboard(context)
    if image is not None:
        return [image]

    return paste_image_files_from_clipboard(context)


def image_clipboard_paste_result() -> OperatorReturn | None:
    # Blender raises RuntimeError when the operator's poll check fails.
    # For Pasty, that is just "no raw image data"; the text-path fallback should still run.
    try:
        return bpy.ops.image.clipboard_paste()
    except RuntimeError:
        return None


def paste_image_data_from_clipboard(context: bpy.types.Context) -> bpy.types.Image | None:
    if context.area is None:
        return None

    keys_before = set(bpy.data.images.keys())
    with temporary_image_editor(context.area):
        result = image_clipboard_paste_result()
    if result != {"FINISHED"}:
        return None

    # The Blender operator returns only a status, not the new image.
    # Compare image keys before and after to find the data-block it created.
    keys_after = set(bpy.data.images.keys())
    new_keys = keys_after - keys_before
    if not new_keys:
        return None

    image_id = new_keys.pop()
    image = bpy.data.images[image_id]

    return mark_pasted_image(image)


def mark_pasted_image(image: bpy.types.Image, source_path: Path | None = None) -> bpy.types.Image:
    # These custom props make future cleanup/move tools possible without a database.
    image["pasty.pasted"] = True
    image["pasty.paste_time"] = datetime.now(UTC).isoformat()
    if source_path is not None:
        image["pasty.source_path"] = str(source_path)

    return image


def paste_image_files_from_clipboard(context: bpy.types.Context) -> list[bpy.types.Image]:
    if context.window_manager is None:
        return []

    # This is Blender's text clipboard, not a direct OS clipboard reader.
    # It covers copied paths and file:// URLs without a platform clipboard layer.
    images = []
    for filepath in image_file_paths_from_clipboard_text(context.window_manager.clipboard):
        image = load_image_file(filepath)
        if image is not None:
            images.append(image)

    return images


def image_file_paths_from_clipboard_text(text: str) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for line in text.splitlines():
        path = image_file_path_from_clipboard_line(line)
        if path is None or path in seen:
            continue
        paths.append(path)
        seen.add(path)
    return paths


def image_file_path_from_clipboard_line(line: str) -> Path | None:
    value = line.strip().strip("\"'")
    # Some file managers put an operation marker before the file list.
    if not value or value in {"copy", "cut"}:
        return None

    parsed = urlparse(value)
    if parsed.scheme == "file":
        # File URLs are the common cross-platform text form for copied files.
        value = unquote(parsed.path)
        if parsed.netloc and parsed.netloc != "localhost":
            value = f"//{parsed.netloc}{value}"
        if sys.platform == "win32" and value.startswith("/") and Path(value[1:]).drive:
            # Windows file URLs look like /C:/path after parsing; pathlib needs C:/path.
            value = value[1:]

    path = Path(value).expanduser()
    if not path.is_absolute():
        # Let Blender resolve //project-relative paths.
        path = Path(bpy.path.abspath(str(path)))
    image_extensions = getattr(bpy.path, "extensions_image", DEFAULT_IMAGE_FILE_EXTENSIONS)
    if path.suffix.lower() not in image_extensions:
        return None
    if not path.is_file():
        return None
    return path


def load_image_file(filepath: Path) -> bpy.types.Image | None:
    try:
        # Reuse an already-loaded image for the same path instead of making duplicates.
        image = bpy.data.images.load(str(filepath), check_existing=True)
    except RuntimeError:
        return None
    return mark_pasted_image(image, filepath)


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
