from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import gettempdir
from typing import TYPE_CHECKING, ClassVar, Protocol

import bpy

from . import preferences

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .blender_types import OperatorReturn

SOURCE_COPIED_FILE = "copied_file"
SOURCE_CLIPBOARD_IMAGE = "clipboard_image"

STORAGE_ORIGINAL_FILE = "original_file"
STORAGE_PACKED = "packed"
STORAGE_PROJECT_FILE = "project_file"
STORAGE_TEMP_FILE = "temp_file"

TEMP_FOLDER_WARNING = (
    "Unsaved .blend: pasted images were saved to Blender's temporary folder. "
    "Save the file, then run Gather Pasted Images."
)

PROP_PASTED = "pasty.pasted"
PROP_PASTE_TIME = "pasty.paste_time"
PROP_SOURCE_KIND = "pasty.source_kind"
PROP_SOURCE_PATH = "pasty.source_path"
PROP_STORAGE_KIND = "pasty.storage_kind"
PROP_MANAGED_PATH = "pasty.managed_path"


class PastedImage(Protocol):
    image: bpy.types.Image
    source_kind: str
    source_path: Path | None


@dataclass(slots=True)
class PreparedPaste:
    images: list[bpy.types.Image]
    used_temp_folder: bool = False


def mark_pasted_image(
    image: bpy.types.Image,
    *,
    source_kind: str,
    source_path: Path | None = None,
    storage_kind: str | None = None,
    managed_path: Path | None = None,
) -> bpy.types.Image:
    # These custom props are the ownership map. They let future gather/cleanup
    # commands act only on files Pasty owns or files the user explicitly gathered.
    image[PROP_PASTED] = True
    image[PROP_PASTE_TIME] = datetime.now(UTC).isoformat()
    image[PROP_SOURCE_KIND] = source_kind
    if source_path is not None:
        image[PROP_SOURCE_PATH] = str(source_path)
    if storage_kind is not None:
        image[PROP_STORAGE_KIND] = storage_kind
    if managed_path is not None:
        image[PROP_MANAGED_PATH] = str(managed_path)
    return image


def prepare_images_for_blender_data(pasted_images: Sequence[PastedImage]) -> PreparedPaste:
    prepared_images = []
    used_temp_folder = False
    for number, pasted_image in enumerate(pasted_images, start=1):
        image, used_temp = prepare_image_for_blender_data(pasted_image, number)
        prepared_images.append(image)
        used_temp_folder = used_temp_folder or used_temp
    return PreparedPaste(prepared_images, used_temp_folder)


def prepare_image_for_blender_data(
    pasted_image: PastedImage, number: int
) -> tuple[bpy.types.Image, bool]:
    preference_values = preferences.values()
    if pasted_image.source_kind == SOURCE_COPIED_FILE:
        if preference_values.copied_image_files == preferences.COPIED_FILES_COPY_TO_FOLDER:
            return copy_source_image_to_managed_file(pasted_image)
        mark_pasted_image(
            pasted_image.image,
            source_kind=SOURCE_COPIED_FILE,
            source_path=pasted_image.source_path,
            storage_kind=STORAGE_ORIGINAL_FILE,
        )
        return pasted_image.image, False

    if preference_values.clipboard_images == preferences.CLIPBOARD_IMAGES_SAVE_TO_FOLDER:
        return save_image_to_managed_file(pasted_image.image, number)

    pack_clipboard_image(pasted_image.image, number)
    return pasted_image.image, False


def file_path_for_sequencer(pasted_image: PastedImage, number: int) -> tuple[Path, bool]:
    if pasted_image.source_kind == SOURCE_COPIED_FILE:
        if preferences.values().copied_image_files == preferences.COPIED_FILES_COPY_TO_FOLDER:
            image, used_temp = copy_source_image_to_managed_file(pasted_image)
            filepath = current_image_path(image)
            if filepath is None:
                msg = "Copied image file has no filepath"
                raise RuntimeError(msg)
            return filepath, used_temp

        if pasted_image.source_path is None:
            msg = "Copied image source path is missing"
            raise RuntimeError(msg)
        return pasted_image.source_path, False

    image, used_temp = save_image_to_managed_file(pasted_image.image, number)
    filepath = current_image_path(image)
    if filepath is None:
        msg = "Saved clipboard image has no filepath"
        raise RuntimeError(msg)
    return filepath, used_temp


def pack_clipboard_image(image: bpy.types.Image, number: int = 1) -> None:
    if image.packed_file is None:
        image.pack()
    image.name = generated_image_filename(number, ".png")
    mark_pasted_image(image, source_kind=SOURCE_CLIPBOARD_IMAGE, storage_kind=STORAGE_PACKED)


def copy_source_image_to_managed_file(pasted_image: PastedImage) -> tuple[bpy.types.Image, bool]:
    if pasted_image.source_path is None:
        msg = "Copied image source path is missing"
        raise RuntimeError(msg)

    source_path = pasted_image.source_path
    storage_kind = target_storage_kind()
    target_directory = managed_images_dir()
    existing_path = existing_managed_path_for_source(source_path, storage_kind, target_directory)
    used_temp = not bpy.data.filepath
    if existing_path is None:
        filename = managed_filename_for_source(source_path)
        destination = unique_path(target_directory, filename)
        shutil.copy2(source_path, destination)
    else:
        destination = existing_path

    image = bpy.data.images.load(str(destination), check_existing=True)
    mark_pasted_image(
        image,
        source_kind=SOURCE_COPIED_FILE,
        source_path=source_path,
        storage_kind=storage_kind,
        managed_path=destination,
    )
    image.filepath_raw = blender_path(destination)
    return image, used_temp


def save_image_to_managed_file(image: bpy.types.Image, number: int) -> tuple[bpy.types.Image, bool]:
    existing_path = managed_path_from_image(image)
    if existing_path is not None and existing_path.exists():
        return image, image.get(PROP_STORAGE_KIND) == STORAGE_TEMP_FILE

    destination = unique_path(managed_images_dir(), generated_image_filename(number, ".png"))
    image.file_format = "PNG"
    image.filepath_raw = str(destination)
    try:
        image.save()
    except RuntimeError:
        # Blender's save_render path works for generated clipboard images when
        # save() cannot initialize normal image-save options.
        image.save_render(str(destination))
    image.name = destination.name
    image.filepath_raw = blender_path(destination)
    mark_pasted_image(
        image,
        source_kind=SOURCE_CLIPBOARD_IMAGE,
        storage_kind=target_storage_kind(),
        managed_path=destination,
    )
    return image, not bpy.data.filepath


def gather_pasted_images() -> int:
    if not bpy.data.filepath:
        msg = "Save the .blend first"
        raise RuntimeError(msg)

    gathered = 0
    for image in bpy.data.images:
        if not image.get(PROP_PASTED):
            continue

        storage_kind = image.get(PROP_STORAGE_KIND)
        if storage_kind not in {STORAGE_ORIGINAL_FILE, STORAGE_TEMP_FILE}:
            continue

        old_path = path_for_gather(image)
        if old_path is None or not old_path.exists():
            continue

        destination = unique_path(project_images_dir(), gathered_filename(old_path))
        shutil.copy2(old_path, destination)
        image.filepath_raw = blender_path(destination)
        update_sequence_image_paths(old_path, destination)
        mark_pasted_image(
            image,
            source_kind=str(image.get(PROP_SOURCE_KIND, SOURCE_COPIED_FILE)),
            source_path=source_path_from_image(image),
            storage_kind=STORAGE_PROJECT_FILE,
            managed_path=destination,
        )

        if storage_kind == STORAGE_TEMP_FILE:
            old_path.unlink(missing_ok=True)
        gathered += 1
    return gathered


def path_for_gather(image: bpy.types.Image) -> Path | None:
    managed_path = managed_path_from_image(image)
    if managed_path is not None:
        return managed_path

    filepath = current_image_path(image)
    if filepath is not None:
        return filepath

    return source_path_from_image(image)


def source_path_from_image(image: bpy.types.Image) -> Path | None:
    source_path = image.get(PROP_SOURCE_PATH)
    if not source_path:
        return None
    return Path(str(source_path))


def managed_path_from_image(image: bpy.types.Image) -> Path | None:
    managed_path = image.get(PROP_MANAGED_PATH)
    if not managed_path:
        return current_image_path(image)
    return Path(str(managed_path))


def current_image_path(image: bpy.types.Image) -> Path | None:
    filepath = image.filepath or image.filepath_raw
    if not filepath:
        return None
    absolute_path = bpy.path.abspath(filepath)
    if not absolute_path:
        return None
    return Path(absolute_path)


def target_storage_kind() -> str:
    if bpy.data.filepath:
        return STORAGE_PROJECT_FILE
    return STORAGE_TEMP_FILE


def managed_images_dir() -> Path:
    if bpy.data.filepath:
        return project_images_dir()
    directory = Path(getattr(bpy.app, "tempdir", "") or gettempdir()) / "pasty"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def project_images_dir() -> Path:
    directory = Path(bpy.path.abspath(f"//{project_images_folder()}"))
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def project_images_folder() -> str:
    folder = preferences.values().pasted_images_folder.strip()
    if not folder:
        folder = preferences.DEFAULT_PASTED_IMAGES_FOLDER

    # Keep this relative to the .blend. Absolute paths and parent traversal make
    # the setting behave like a custom file manager, which Pasty is not.
    parts = [
        part for part in folder.replace("\\", "/").split("/") if part and part not in {".", ".."}
    ]
    return "/".join(parts) or preferences.DEFAULT_PASTED_IMAGES_FOLDER


def managed_filename_for_source(source_path: Path) -> str:
    return safe_filename(source_path.name)


def gathered_filename(source_path: Path) -> str:
    return safe_filename(source_path.name)


def generated_image_filename(number: int, suffix: str) -> str:
    pattern = preferences.values().generated_image_name or preferences.DEFAULT_GENERATED_IMAGE_NAME
    return preferences.render_generated_image_name(pattern, number=number, suffix=suffix)


def safe_filename(filename: str) -> str:
    return preferences.file_safe_name(filename, fallback="pasted-image.png")


def unique_path(directory: Path, filename: str) -> Path:
    path = directory / filename
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    for index in range(2, 10_000):
        candidate = directory / f"{stem}-{index:03d}{suffix}"
        if not candidate.exists():
            return candidate

    msg = f"Could not find a free filename in {directory}"
    raise RuntimeError(msg)


def existing_managed_path_for_source(
    source_path: Path, storage_kind: str, target_directory: Path
) -> Path | None:
    target_directory = target_directory.resolve(strict=False)
    for image in bpy.data.images:
        if image.get(PROP_SOURCE_PATH) != str(source_path):
            continue
        if image.get(PROP_STORAGE_KIND) != storage_kind:
            continue
        managed_path = managed_path_from_image(image)
        if (
            managed_path is not None
            and managed_path.exists()
            and managed_path.resolve(strict=False).is_relative_to(target_directory)
        ):
            return managed_path
    return None


def blender_path(filepath: Path) -> str:
    if not bpy.data.filepath:
        return str(filepath)
    try:
        return bpy.path.relpath(str(filepath))
    except ValueError:
        return str(filepath)


def update_sequence_image_paths(old_path: Path, new_path: Path) -> None:
    old_path = old_path.resolve(strict=False)
    for scene in bpy.data.scenes:
        sequence_editor = scene.sequence_editor
        if sequence_editor is None:
            continue
        for strip in sequence_editor.strips_all:
            if strip.type != "IMAGE":
                continue
            directory = Path(bpy.path.abspath(strip.directory))
            for element in strip.elements:
                element_path = (directory / element.filename).resolve(strict=False)
                if element_path != old_path:
                    continue
                strip.directory = directory_path_for_strip(new_path.parent)
                element.filename = new_path.name


def directory_path_for_strip(directory: Path) -> str:
    directory_path = blender_path(directory)
    if directory_path.endswith(("/", "\\")):
        return directory_path
    return f"{directory_path}/"


class PASTY_OT_gather_pasted_images(bpy.types.Operator):
    """Gather pasted images beside the .blend"""

    bl_idname = "pasty.gather_pasted_images"
    bl_label = "Gather Pasted Images"
    bl_options: ClassVar[set[str]] = {"UNDO_GROUPED"}  # ty: ignore[invalid-attribute-override]

    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        del context
        try:
            gathered = gather_pasted_images()
        except RuntimeError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        if gathered == 0:
            self.report({"INFO"}, "No pasted images need gathering")
            return {"FINISHED"}

        self.report(
            {"INFO"},
            f"Gathered {gathered} pasted images into //{project_images_folder()}. "
            "Save the .blend to keep these paths.",
        )
        return {"FINISHED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        del context
        return bool(bpy.data.filepath)


def external_data_menu_draw(self: bpy.types.Menu, _context: bpy.types.Context) -> None:
    layout = self.layout
    if layout is None:
        return
    layout.separator()
    layout.operator(PASTY_OT_gather_pasted_images.bl_idname, icon="FILE_FOLDER")


classes = (PASTY_OT_gather_pasted_images,)

menu_hooks = ((bpy.types.TOPBAR_MT_file_external_data, external_data_menu_draw),)
