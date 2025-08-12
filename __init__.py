import re
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import datetime
from typing import ClassVar

import bpy

# region Image Editor Utilities


@contextmanager
def image_editor() -> Generator[bpy.types.Area, None, None]:
    """Context manager to switch the active area to the Image Editor."""

    area = bpy.context.area
    assert area is not None, "No active area found"

    former_area_type = area.type
    former_ui_type = getattr(area, "ui_type", None)

    area.type = "IMAGE_EDITOR"
    try:
        yield area
    finally:
        area.type = former_area_type
        if former_ui_type is not None:
            area.ui_type = former_ui_type


def paste_image_from_clipboard() -> bpy.types.Image:
    """Paste an image from the clipboard into the image editor.

    Returns:
        bpy.types.Image: The newly created image object from the clipboard.
    """

    keys_before = set(bpy.data.images.keys())
    with image_editor():
        bpy.ops.image.clipboard_paste()
    keys_after = set(bpy.data.images.keys())

    assert keys_after != keys_before, "No new image was pasted from the clipboard"
    image_id = (keys_after - keys_before).pop()
    return bpy.data.images[image_id]


def insert_image_as_reference(context: bpy.types.Context) -> None:
    """Insert an image from the clipboard as a reference object in the 3D View."""

    image = paste_image_from_clipboard()
    bpy.ops.object.empty_add(type="IMAGE", radius=5.0, align="VIEW")
    assert context.active_object is not None, "No active object found after adding empty"
    context.active_object.data = image  # ty: ignore[invalid-assignment]


def can_paste_from_clipboard() -> bool:
    with image_editor():
        return bpy.ops.image.clipboard_paste.poll()  # ty: ignore[unresolved-attribute]


# endregion


# region Template Expansion


CALLABLE_VARIABLES: dict[str, Callable[[], str]] = {
    "day": lambda: datetime.now().strftime("%A"),
    "date": lambda: datetime.now().strftime("%Y-%m-%d"),
    "time": lambda: datetime.now().strftime("%H:%M:%S"),
    "hour": lambda: datetime.now().strftime("%H"),
    "minute": lambda: datetime.now().strftime("%M"),
}


FILTERS: dict[str, Callable[[str], str]] = {
    "upper": str.upper,
    "lower": str.lower,
    "title": str.title,
    "strip": str.strip,
    # Example: Reverse string
    "reverse": lambda s: s[::-1],
}


PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\|?([a-zA-Z_]*)\}")


def expand_template(template: str, extra_vars: dict[str, Callable[[], str]] | None = None) -> str:
    if extra_vars:
        CALLABLE_VARIABLES.update(extra_vars)

    def replacer(match):
        var_name = match.group(1)
        filter_name = match.group(2)

        # Get value
        value = CALLABLE_VARIABLES.get(var_name, "{" + var_name + "}")
        if callable(value):
            value = value()

        # Apply filter if exists
        if filter_name:
            func = FILTERS.get(filter_name)
            if func:
                value = func(str(value))

        return str(value)

    return PATTERN.sub(replacer, template)


# endregion


# region View3D Paste Reference Operator


class PASTY_OT_view3d_paste_reference(bpy.types.Operator):
    """Paste image from the clipboard as a reference"""

    bl_idname = "pasty.view3d_paste_reference"
    bl_label = "Paste as Reference"
    bl_options: ClassVar[set[str]] = {"UNDO_GROUPED"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        insert_image_as_reference(context)
        return {"FINISHED"}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return (
            context.area is not None
            and context.area.type == "VIEW_3D"
            and context.area.ui_type == "VIEW_3D"
            and context.mode == "OBJECT"
            and can_paste_from_clipboard()
        )


def view3d_paste_reference_image_add_menu_draw(self, context: bpy.types.Context) -> None:
    """Draw the Paste as Reference operator in the 3D View Add Image menu."""
    self.layout.separator()
    self.layout.operator(PASTY_OT_view3d_paste_reference.bl_idname, icon="IMAGE_REFERENCE")


def view3d_paste_reference_image_add_menu_km(
    kc: bpy.types.KeyConfig,
) -> tuple[bpy.types.KeyMap, bpy.types.KeyMapItem]:
    """Add a keymap item for the Paste as Reference operator in the 3D View."""
    km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
    kmi = km.keymap_items.new(
        PASTY_OT_view3d_paste_reference.bl_idname,
        type="V",
        value="PRESS",
        ctrl=True,
        shift=True,
        alt=True,
    )
    return km, kmi


# endregion


# region View3D Paste Plane Operator


class PASTY_OT_view3d_paste_plane(bpy.types.Operator):
    """Paste image from the clipboard as a plane"""

    bl_idname = "pasty.view3d_paste_plane"
    bl_label = "Paste as Plane"
    bl_options: ClassVar[set[str]] = {"UNDO_GROUPED"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        insert_image_as_reference(context)
        bpy.ops.image.convert_to_mesh_plane()
        return {"FINISHED"}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return (
            context.area is not None
            and context.area.type == "VIEW_3D"
            and context.area.ui_type == "VIEW_3D"
            and context.mode == "OBJECT"
            and can_paste_from_clipboard()
        )


def view3d_paste_plane_image_add_menu_draw(self, context: bpy.types.Context) -> None:
    """Draw the Paste as Reference operator in the 3D View Add Image menu."""
    self.layout.operator(PASTY_OT_view3d_paste_plane.bl_idname, icon="FILE_IMAGE")


def view3d_paste_plane_image_add_menu_km(
    kc: bpy.types.KeyConfig,
) -> tuple[bpy.types.KeyMap, bpy.types.KeyMapItem]:
    """Add a keymap item for the Paste as Plane operator in the 3D View."""
    km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
    kmi = km.keymap_items.new(
        PASTY_OT_view3d_paste_plane.bl_idname, type="V", value="PRESS", ctrl=True, shift=True
    )
    return km, kmi


# endregion


# region Sequence Editor Paste Operator


class PASTY_OT_sequence_editor_paste(bpy.types.Operator):
    """Paste images from the clipboard"""

    bl_idname = "pasty.sequence_editor_paste"
    bl_label = "Paste from Clipboard"
    bl_options: ClassVar[set[str]] = {"UNDO_GROUPED"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        assert context.scene is not None and context.scene.sequence_editor is not None, (
            "No Sequence Editor found in the current scene"
        )

        sequences = context.scene.sequence_editor.sequences
        current_frame = context.scene.frame_current
        image_strip = sequences.new_image(
            name="Pasted Image",
            filepath=paste_image_from_clipboard().filepath,
            channel=1,
            frame_start=current_frame,
        )
        image_strip.frame_final_end = current_frame + 50
        return {"FINISHED"}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return (
            context.area is not None
            and context.area.type == "SEQUENCE_EDITOR"
            and can_paste_from_clipboard()
        )


def sequence_editor_paste_context_menu_draw(self, context: bpy.types.Context):
    """Draw the Paste operator in the Sequence Editor context menu."""
    self.layout.separator()
    self.layout.operator(PASTY_OT_sequence_editor_paste.bl_idname, icon="IMAGE_PLANE")


def sequence_editor_paste_context_menu_km(
    kc: bpy.types.KeyConfig,
) -> tuple[bpy.types.KeyMap, bpy.types.KeyMapItem]:
    """Add a keymap item for the Paste from Clipboard operator in the Sequence Editor."""
    km = kc.keymaps.new(name="Sequencer", space_type="SEQUENCE_EDITOR")
    kmi = km.keymap_items.new(
        PASTY_OT_sequence_editor_paste.bl_idname,
        type="V",
        value="PRESS",
        ctrl=True,
        shift=True,
        alt=True,
    )
    return km, kmi


# endregion


# region Shader Editor Paste Operator


class PASTY_OT_shader_editor_paste(bpy.types.Operator):
    """Paste images from the clipboard"""

    bl_idname = "pasty.shader_editor_paste"
    bl_label = "Paste from Clipboard"
    bl_options: ClassVar[set[str]] = {"UNDO_GROUPED"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        assert context.space_data is not None, "No Space Data found in the current context"
        assert isinstance(context.space_data, bpy.types.SpaceNodeEditor), (
            "Current space data is not a Node Editor"
        )
        assert context.space_data.edit_tree is not None, (
            "No active node tree found in the Node Editor"
        )

        node_image = context.space_data.edit_tree.nodes.new("ShaderNodeTexImage")

        location_x, location_y = context.space_data.cursor_location
        node_image.location = location_x, location_y
        # Offset location for next node
        location_y += 300

        image = paste_image_from_clipboard()
        node_image.image = image  # ty: ignore[unresolved-attribute]
        return {"FINISHED"}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        if (
            context.area is not None
            and context.area.type == "NODE_EDITOR"
            and context.area.ui_type == "ShaderNodeTree"
        ):
            assert isinstance(context.space_data, bpy.types.SpaceNodeEditor), (
                "Current space data is not a Node Editor"
            )
            return context.space_data.edit_tree is not None and can_paste_from_clipboard()
        return False


def shader_editor_paste_context_menu_draw(self, context: bpy.types.Context):
    """Draw the Paste operator in the Sequence Editor context menu."""
    self.layout.operator(PASTY_OT_shader_editor_paste.bl_idname, icon="FILE_IMAGE")


def shader_editor_paste_context_menu_km(
    kc: bpy.types.KeyConfig,
) -> tuple[bpy.types.KeyMap, bpy.types.KeyMapItem]:
    """Add a keymap item for the Paste from Clipboard operator in the Sequence Editor."""
    km = kc.keymaps.new(name="Node Editor", space_type="NODE_EDITOR")
    kmi = km.keymap_items.new(
        PASTY_OT_shader_editor_paste.bl_idname, type="V", value="PRESS", ctrl=True, shift=True
    )
    return km, kmi


# endregion


# region Register Classes and Keymaps

classes = (
    PASTY_OT_view3d_paste_reference,
    PASTY_OT_view3d_paste_plane,
    PASTY_OT_sequence_editor_paste,
    PASTY_OT_shader_editor_paste,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
        print(f"Registered {cls.__name__}")
    bpy.types.VIEW3D_MT_add.append(view3d_paste_reference_image_add_menu_draw)
    bpy.types.VIEW3D_MT_add.append(view3d_paste_plane_image_add_menu_draw)
    bpy.types.SEQUENCER_MT_context_menu.append(sequence_editor_paste_context_menu_draw)
    bpy.types.NODE_MT_context_menu.append(shader_editor_paste_context_menu_draw)


def unregister():
    bpy.types.NODE_MT_context_menu.remove(shader_editor_paste_context_menu_draw)
    bpy.types.SEQUENCER_MT_context_menu.append(sequence_editor_paste_context_menu_draw)
    bpy.types.VIEW3D_MT_add.remove(view3d_paste_plane_image_add_menu_draw)
    bpy.types.VIEW3D_MT_add.remove(view3d_paste_reference_image_add_menu_draw)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
        print(f"Unregistered {cls.__name__}")


addon_keymaps = []

keymap_functions = (
    view3d_paste_reference_image_add_menu_km,
    view3d_paste_plane_image_add_menu_km,
    sequence_editor_paste_context_menu_km,
)


def register_keymaps():
    if bpy.context.window_manager is None:
        return

    kc = bpy.context.window_manager.keyconfigs.addon
    if not kc:
        return

    for km_func in keymap_functions:
        km, kmi = km_func(kc)
        addon_keymaps.append((km, kmi))
        print(f"Registered keymap {km.name} for {kmi.idname}")


def unregister_keymaps():
    if bpy.context.window_manager is None:
        return

    kc = bpy.context.window_manager.keyconfigs.addon
    if not kc:
        return

    for km, kmi in addon_keymaps:
        kc.keymaps.remove(km)
        print(f"Unregistered keymap {km.name} for {kmi.idname}")


# endregion
