from dataclasses import dataclass
from typing import ClassVar

import bpy

from ..blender_types import OperatorReturn
from ..clipboard import paste_failed, paste_images_from_clipboard
from ..preferences import DEFAULT_SEQUENCE_STRIP_DURATION, values
from ..storage import TEMP_FOLDER_WARNING, blender_path, file_path_for_sequencer

SEQUENCE_STRIP_DURATION = DEFAULT_SEQUENCE_STRIP_DURATION
SEQUENCE_MAX_CHANNEL = 128


@dataclass(slots=True)
class SequencePasteResult:
    strips: list
    used_temp_folder: bool = False


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


def sequence_strip_duration() -> int:
    return values().sequence_strip_duration


def add_sequence_image_strips(strips, pasted_images, frame_start: int) -> SequencePasteResult:
    image_strips = []
    used_temp_folder = False
    try:
        strip_duration = sequence_strip_duration()
        for offset_index, pasted_image in enumerate(pasted_images):
            # Put multiple pasted images in a row so they do not overlap by default.
            strip_start = frame_start + (offset_index * strip_duration)
            strip_end = strip_start + strip_duration
            channel = first_free_sequence_channel(strips, strip_start, strip_end)
            filepath, used_temp = file_path_for_sequencer(pasted_image, offset_index + 1)
            used_temp_folder = used_temp_folder or used_temp
            image_strip = strips.new_image(
                name=pasted_image.image.name,
                filepath=blender_path(filepath),
                channel=channel,
                frame_start=strip_start,
            )
            set_sequence_strip_end(image_strip, strip_end)
            image_strips.append(image_strip)
    except RuntimeError:
        # Avoid leaving half-created strips if a later file cannot be added.
        for image_strip in image_strips:
            strips.remove(image_strip)
        raise
    return SequencePasteResult(image_strips, used_temp_folder)


class PASTY_OT_sequence_editor_paste(bpy.types.Operator):
    """Paste images from the clipboard"""

    bl_idname = "pasty.sequence_editor_paste"
    bl_label = "Paste Image Strip"
    bl_options: ClassVar[set[str]] = {"UNDO_GROUPED"}  # ty: ignore[invalid-attribute-override]

    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        if context.scene is None:
            self.report({"ERROR"}, "No active scene")
            return {"CANCELLED"}

        pasted_images = paste_images_from_clipboard(context)
        if not pasted_images:
            return paste_failed(self)

        sequence_editor = context.scene.sequence_editor or context.scene.sequence_editor_create()
        strips = sequence_collection(sequence_editor)
        current_frame = context.scene.frame_current
        try:
            result = add_sequence_image_strips(strips, pasted_images, current_frame)
        except RuntimeError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        if result.used_temp_folder:
            self.report({"WARNING"}, TEMP_FOLDER_WARNING)

        return {"FINISHED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Keep poll cheap. Blender calls it while drawing UI, so do not inspect the clipboard.
        return context.area is not None and context.area.type == "SEQUENCE_EDITOR"


def sequence_editor_paste_context_menu_draw(self, _context: bpy.types.Context) -> None:
    """Draw the Paste operator in the Sequence Editor context menu."""
    self.layout.separator()
    self.layout.operator(PASTY_OT_sequence_editor_paste.bl_idname, icon="FILE_IMAGE")


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
