import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import bpy

COPIED_FILES_USE_ORIGINAL = "USE_ORIGINAL"
COPIED_FILES_COPY_TO_FOLDER = "COPY_TO_FOLDER"
CLIPBOARD_IMAGES_PACK = "PACK"
CLIPBOARD_IMAGES_SAVE_TO_FOLDER = "SAVE_TO_FOLDER"

DEFAULT_PASTED_IMAGES_FOLDER = "pasted-images"
DEFAULT_GENERATED_IMAGE_NAME = "pasted-{date}-{time}-{number}"
DEFAULT_SEQUENCE_STRIP_DURATION = 50
PREFERENCE_LABEL_WIDTH = 0.30


def generated_image_extension(_preferences: object) -> str:
    return ".png"


@dataclass(frozen=True, slots=True)
class PastyPreferences:
    copied_image_files: str = COPIED_FILES_USE_ORIGINAL
    clipboard_images: str = CLIPBOARD_IMAGES_PACK
    pasted_images_folder: str = DEFAULT_PASTED_IMAGES_FOLDER
    generated_image_name: str = DEFAULT_GENERATED_IMAGE_NAME
    sequence_strip_duration: int = DEFAULT_SEQUENCE_STRIP_DURATION


def addon_package_name() -> str:
    package_name = __package__ or ""
    return package_name.removesuffix(".addon")


def get_addon_preferences() -> "PASTY_AddonPreferences | None":
    blender_preferences = bpy.context.preferences
    if blender_preferences is None:
        return None

    addon = blender_preferences.addons.get(addon_package_name())
    if addon is None:
        return None
    return addon.preferences


def values() -> PastyPreferences:
    preferences = get_addon_preferences()
    if preferences is None:
        return PastyPreferences()

    return PastyPreferences(
        copied_image_files=preferences.copied_image_files,
        clipboard_images=preferences.clipboard_images,
        pasted_images_folder=preferences.pasted_images_folder,
        generated_image_name=preferences.generated_image_name,
        sequence_strip_duration=preferences.sequence_strip_duration,
    )


class PASTY_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = addon_package_name()

    copied_image_files: bpy.props.EnumProperty(  # ty: ignore[invalid-type-form]
        name="Copied Image Files",
        description="How Pasty handles image files copied from your disk",
        items=(
            (
                COPIED_FILES_USE_ORIGINAL,
                "Use Originals",
                "Keep Blender linked to the files you copied",
            ),
            (
                COPIED_FILES_COPY_TO_FOLDER,
                "Copy to Folder",
                "Copy pasted files into the Pasted Images Folder",
            ),
        ),
        default=COPIED_FILES_USE_ORIGINAL,
    )
    clipboard_images: bpy.props.EnumProperty(  # ty: ignore[invalid-type-form]
        name="Clipboard Images",
        description="How Pasty keeps screenshots and copied image pixels",
        items=(
            (
                CLIPBOARD_IMAGES_PACK,
                "Pack into .blend",
                "Store pasted clipboard images inside the .blend",
            ),
            (
                CLIPBOARD_IMAGES_SAVE_TO_FOLDER,
                "Save to Folder",
                "Save generated clipboard images into the Pasted Images Folder",
            ),
        ),
        default=CLIPBOARD_IMAGES_PACK,
    )
    pasted_images_folder: bpy.props.StringProperty(  # ty: ignore[invalid-type-form]
        name="Pasted Images Folder",
        description="Folder beside the .blend file for pasted image files",
        default=DEFAULT_PASTED_IMAGES_FOLDER,
    )
    generated_image_name: bpy.props.StringProperty(  # ty: ignore[invalid-type-form]
        name="Generated File Name",
        description="Name pattern for generated clipboard PNGs; see README for tokens",
        default=DEFAULT_GENERATED_IMAGE_NAME,
        subtype="FILE_NAME",
    )
    sequence_strip_duration: bpy.props.IntProperty(  # ty: ignore[invalid-type-form]
        name="Still Image Length (Frames)",
        description="Default length for pasted Sequencer image strips",
        default=DEFAULT_SEQUENCE_STRIP_DURATION,
        min=1,
    )
    generated_image_extension: bpy.props.StringProperty(  # ty: ignore[invalid-type-form]
        name="Generated File Extension",
        description="Generated clipboard images are always saved as PNG",
        get=generated_image_extension,
    )

    def draw(self, _context: bpy.types.Context) -> None:
        layout = self.layout
        layout.use_property_split = False
        layout.use_property_decorate = False

        storage = layout.column()
        storage.label(text="Storage")
        enum_row(
            storage,
            "Copied Image Files",
            self,
            "copied_image_files",
            (COPIED_FILES_USE_ORIGINAL, COPIED_FILES_COPY_TO_FOLDER),
        )
        enum_row(
            storage,
            "Clipboard Images",
            self,
            "clipboard_images",
            (CLIPBOARD_IMAGES_PACK, CLIPBOARD_IMAGES_SAVE_TO_FOLDER),
        )
        property_row(storage, "Pasted Images Folder", self, "pasted_images_folder")

        naming = layout.column()
        naming.label(text="Naming")
        filename_template_row(naming, "Generated File Name", self)
        note_row(naming, f"Preview: {generated_name_preview(self.generated_image_name)}")

        sequencer = layout.column()
        sequencer.label(text="Sequencer")
        property_row(sequencer, "Still Image Length (Frames)", self, "sequence_strip_duration")


def labeled_control_row(layout: bpy.types.UILayout, label_text: str) -> bpy.types.UILayout:
    row = layout.row(align=True)
    split = row.split(factor=PREFERENCE_LABEL_WIDTH)
    label = split.column()
    label.alignment = "RIGHT"
    label.label(text=label_text)
    return split.row(align=True)


def enum_row(
    layout: bpy.types.UILayout,
    label_text: str,
    preferences: PASTY_AddonPreferences,
    property_name: str,
    item_identifiers: tuple[str, ...],
) -> None:
    control = labeled_control_row(layout, label_text)
    for item_identifier in item_identifiers:
        control.prop_enum(preferences, property_name, item_identifier)


def property_row(
    layout: bpy.types.UILayout,
    label_text: str,
    preferences: PASTY_AddonPreferences,
    property_name: str,
) -> None:
    control = labeled_control_row(layout, label_text)
    control.prop(preferences, property_name, text="")


def filename_template_row(
    layout: bpy.types.UILayout, label_text: str, preferences: PASTY_AddonPreferences
) -> None:
    control = labeled_control_row(layout, label_text)
    control.prop(preferences, "generated_image_name", text="")
    extension = control.column(align=True)
    extension.alignment = "RIGHT"
    extension.prop(preferences, "generated_image_extension", text="")


def note_row(layout: bpy.types.UILayout, text: str) -> None:
    row = layout.row(align=True)
    split = row.split(factor=PREFERENCE_LABEL_WIDTH)
    split.column()
    note = split.column()
    note.label(text=text)


def generated_name_preview(pattern: str) -> str:
    return render_generated_image_name(pattern, number=1, suffix=".png")


def render_generated_image_name(
    pattern: str,
    *,
    number: int,
    suffix: str = ".png",
    now: datetime | None = None,
    blend_filepath: str | None = None,
) -> str:
    now = now or datetime.now(tz=UTC).astimezone()
    suffix = suffix or ".png"
    suffix = suffix if suffix.startswith(".") else f".{suffix}"
    blend_name = "untitled"
    if blend_filepath is None:
        blend_filepath = bpy.data.filepath
    if blend_filepath:
        blend_name = Path(blend_filepath).stem or blend_name

    name = pattern or DEFAULT_GENERATED_IMAGE_NAME
    name = re.sub(
        r"\{number:(\d+)\}",
        lambda match: str(number).zfill(min(max(int(match.group(1)), 1), 9)),
        name,
    )
    replacements = {
        "{blend}": file_safe_name(blend_name, fallback="untitled"),
        "{date}": now.strftime("%Y%m%d"),
        "{time}": now.strftime("%H%M%S"),
        "{year}": now.strftime("%Y"),
        "{month}": now.strftime("%m"),
        "{day}": now.strftime("%d"),
        "{hour}": now.strftime("%H"),
        "{minute}": now.strftime("%M"),
        "{second}": now.strftime("%S"),
        "{number}": f"{number:03d}",
    }
    for token, value in replacements.items():
        name = name.replace(token, value)
    name = file_safe_name(name, fallback="pasted-image")
    if Path(name).suffix.lower() == suffix.lower():
        return name
    return file_safe_name(f"{name}{suffix}", fallback=f"pasted-image{suffix}")


def file_safe_name(name: str, *, fallback: str) -> str:
    name = re.sub(r"[^\w .-]", "-", name, flags=re.ASCII).strip(" .")
    return name or fallback
