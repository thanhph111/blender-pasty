from datetime import UTC, datetime
from pathlib import Path
from tempfile import gettempdir
from typing import ClassVar

import bpy

from ..blender_types import OperatorReturn
from ..clipboard import paste_failed, paste_images_from_clipboard

SEQUENCE_STRIP_DURATION = 50
SEQUENCE_MAX_CHANNEL = 128


def pasted_images_dir() -> Path:
    if bpy.data.filepath:
        # Saved projects should keep generated clipboard images beside the .blend.
        directory = Path(bpy.path.abspath("//pasty"))
    else:
        # Unsaved projects have no stable project folder yet.
        directory = Path(gettempdir()) / "pasty"

    directory.mkdir(parents=True, exist_ok=True)
    return directory


def saved_image_path(image: bpy.types.Image) -> Path:
    filepath = bpy.path.abspath(image.filepath)
    if filepath:
        return Path(filepath)

    # Raw clipboard images are generated data-blocks. Sequencer strips need a real file.
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    filepath = pasted_images_dir() / f"pasty-{timestamp}.png"
    image.save_render(str(filepath))
    image.filepath_raw = str(filepath)
    image["pasty.filepath"] = str(filepath)
    return filepath


def sequence_collection(sequence_editor):
    # Blender 5 renamed top-level Sequencer access from sequences to strips.
    collection = getattr(sequence_editor, "strips", None)
    if collection is not None:
        return collection
    return sequence_editor.sequences


def sequence_strip_start(strip) -> float:
    # Blender 5.x added handle names and warns that frame_final_* will go away in 6.0.
    # Keep the old path so Blender 4.2 LTS still works.
    if hasattr(strip, "left_handle"):
        return strip.left_handle
    return strip.frame_final_start


def sequence_strip_end(strip) -> float:
    # See sequence_strip_start() for why this checks both API names.
    if hasattr(strip, "right_handle"):
        return strip.right_handle
    return strip.frame_final_end


def set_sequence_strip_end(strip, frame_end: int) -> None:
    # See sequence_strip_start() for why this writes through both API names.
    if hasattr(strip, "right_handle"):
        strip.right_handle = frame_end
        return
    strip.frame_final_end = frame_end


def strip_overlaps_frame_range(strip, frame_start: int, frame_end: int) -> bool:
    return sequence_strip_start(strip) < frame_end and frame_start < sequence_strip_end(strip)


def first_free_sequence_channel(strips, frame_start: int, frame_end: int) -> int:
    # Blender Sequencer channels are 1-based and currently capped at 128.
    for channel in range(1, SEQUENCE_MAX_CHANNEL + 1):
        if all(
            strip.channel != channel
            or not strip_overlaps_frame_range(strip, frame_start, frame_end)
            for strip in strips
        ):
            return channel

    msg = "No free Sequencer channel available"
    raise RuntimeError(msg)


def add_sequence_image_strips(strips, images: list[bpy.types.Image], frame_start: int) -> list:
    image_strips = []
    try:
        for offset_index, image in enumerate(images):
            # Put multiple pasted images in a row so they do not overlap by default.
            strip_start = frame_start + (offset_index * SEQUENCE_STRIP_DURATION)
            strip_end = strip_start + SEQUENCE_STRIP_DURATION
            channel = first_free_sequence_channel(strips, strip_start, strip_end)
            filepath = saved_image_path(image)
            image_strip = strips.new_image(
                name=image.name, filepath=str(filepath), channel=channel, frame_start=strip_start
            )
            set_sequence_strip_end(image_strip, strip_end)
            image_strips.append(image_strip)
    except RuntimeError:
        # Avoid leaving half-created strips if a later file cannot be added.
        for image_strip in image_strips:
            strips.remove(image_strip)
        raise
    return image_strips


class PASTY_OT_sequence_editor_paste(bpy.types.Operator):
    """Paste images from the clipboard"""

    bl_idname = "pasty.sequence_editor_paste"
    bl_label = "Paste from Clipboard"
    bl_options: ClassVar[set[str]] = {"UNDO_GROUPED"}  # ty: ignore[invalid-attribute-override]

    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        if context.scene is None:
            self.report({"ERROR"}, "No active scene")
            return {"CANCELLED"}

        images = paste_images_from_clipboard(context)
        if not images:
            return paste_failed(self)

        sequence_editor = context.scene.sequence_editor or context.scene.sequence_editor_create()
        strips = sequence_collection(sequence_editor)
        current_frame = context.scene.frame_current
        # saved_image_path() gives generated images a filepath, so check this before saving.
        will_save_generated_images_to_temp = not bpy.data.filepath and any(
            not bpy.path.abspath(image.filepath) for image in images
        )
        try:
            add_sequence_image_strips(strips, images, current_frame)
        except RuntimeError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        if will_save_generated_images_to_temp:
            self.report({"WARNING"}, "Unsaved .blend: pasted images were saved to the temp folder")

        return {"FINISHED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Keep poll cheap. Blender calls it while drawing UI, so do not inspect the clipboard.
        return context.area is not None and context.area.type == "SEQUENCE_EDITOR"


def sequence_editor_paste_context_menu_draw(self, _context: bpy.types.Context) -> None:
    """Draw the Paste operator in the Sequence Editor context menu."""
    self.layout.separator()
    self.layout.operator(PASTY_OT_sequence_editor_paste.bl_idname, icon="IMAGE_PLANE")


classes = (PASTY_OT_sequence_editor_paste,)

menu_hooks = ((bpy.types.SEQUENCER_MT_context_menu, sequence_editor_paste_context_menu_draw),)

keymap_specs = (
    (
        "Sequencer",
        "SEQUENCE_EDITOR",
        PASTY_OT_sequence_editor_paste.bl_idname,
        {"ctrl": True, "shift": True, "alt": True},
    ),
)
