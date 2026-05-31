from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import gettempdir
from typing import ClassVar, Literal

import bpy

OperatorReturn = set[Literal["RUNNING_MODAL", "CANCELLED", "FINISHED", "PASS_THROUGH", "INTERFACE"]]
SEQUENCE_STRIP_DURATION = 50
SEQUENCE_MAX_CHANNEL = 128

# region Image Editor Utilities


@contextmanager
def temporary_image_editor(area: bpy.types.Area) -> Generator[bpy.types.Area, None, None]:
    """Temporarily switch an area to the Image Editor."""

    former_area_type = area.type
    former_ui_type = getattr(area, "ui_type", None)

    area.type = "IMAGE_EDITOR"
    try:
        yield area
    finally:
        area.type = former_area_type
        if former_ui_type is not None:
            area.ui_type = former_ui_type


def paste_image_from_clipboard(context: bpy.types.Context) -> bpy.types.Image | None:
    """Paste an image from the clipboard into a new Blender image data-block."""
    if context.area is None:
        return None

    keys_before = set(bpy.data.images.keys())
    with temporary_image_editor(context.area):
        result = bpy.ops.image.clipboard_paste()
    if result != {"FINISHED"}:
        return None

    keys_after = set(bpy.data.images.keys())
    new_keys = keys_after - keys_before
    if not new_keys:
        return None

    image_id = new_keys.pop()
    image = bpy.data.images[image_id]

    image["pasty.pasted"] = True
    image["pasty.paste_time"] = datetime.now(UTC).isoformat()

    return image


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
            return bpy.ops.image.clipboard_copy() == {"FINISHED"}
        finally:
            space.image = previous_image


def image_from_node(node) -> bpy.types.Image | None:
    if node is not None and node.bl_idname == "ShaderNodeTexImage":
        return node.image
    return None


def image_from_material(material: bpy.types.Material | None) -> bpy.types.Image | None:
    if material is None or not material.use_nodes or material.node_tree is None:
        return None

    nodes = material.node_tree.nodes
    active_image = image_from_node(nodes.active)
    if active_image is not None:
        return active_image

    for node in nodes:
        image = image_from_node(node)
        if image is not None:
            return image

    return None


def image_from_object(obj: bpy.types.Object | None) -> bpy.types.Image | None:
    if obj is None:
        return None

    if obj.type == "EMPTY" and obj.empty_display_type == "IMAGE":
        if isinstance(obj.data, bpy.types.Image):
            return obj.data
        return None

    return image_from_material(obj.active_material)


def active_shader_image(context: bpy.types.Context) -> bpy.types.Image | None:
    if context.space_data is None or not isinstance(context.space_data, bpy.types.SpaceNodeEditor):
        return None
    if context.space_data.edit_tree is None:
        return None

    nodes = context.space_data.edit_tree.nodes
    active_image = image_from_node(nodes.active)
    if active_image is not None:
        return active_image

    for node in nodes:
        if node.select:
            image = image_from_node(node)
            if image is not None:
                return image

    return None


def insert_image_as_reference(context: bpy.types.Context, image: bpy.types.Image) -> bool:
    """Insert a pasted image as a reference object in the 3D View."""
    bpy.ops.object.empty_add(type="IMAGE", radius=5.0, align="VIEW")
    if context.active_object is None:
        return False

    context.active_object.data = image  # ty: ignore[invalid-assignment]
    return True


def pasted_images_dir() -> Path:
    if bpy.data.filepath:
        directory = Path(bpy.path.abspath("//pasty"))
    else:
        directory = Path(gettempdir()) / "pasty"

    directory.mkdir(parents=True, exist_ok=True)
    return directory


def saved_image_path(image: bpy.types.Image) -> Path:
    filepath = bpy.path.abspath(image.filepath)
    if filepath:
        return Path(filepath)

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    filepath = pasted_images_dir() / f"pasty-{timestamp}.png"
    image.save_render(str(filepath))
    image.filepath_raw = str(filepath)
    image["pasty.filepath"] = str(filepath)
    return filepath


def sequence_collection(sequence_editor):
    collection = getattr(sequence_editor, "strips", None)
    if collection is not None:
        return collection
    return sequence_editor.sequences


def strip_overlaps_frame_range(strip, frame_start: int, frame_end: int) -> bool:
    return strip.frame_final_start < frame_end and frame_start < strip.frame_final_end


def first_free_sequence_channel(strips, frame_start: int, frame_end: int) -> int:
    for channel in range(1, SEQUENCE_MAX_CHANNEL + 1):
        if all(
            strip.channel != channel
            or not strip_overlaps_frame_range(strip, frame_start, frame_end)
            for strip in strips
        ):
            return channel

    msg = "No free Sequencer channel available"
    raise RuntimeError(msg)


# endregion


# region View3D Copy Image Operator


class PASTY_OT_view3d_copy_image(bpy.types.Operator):
    """Copy image from the active object to the clipboard"""

    bl_idname = "pasty.view3d_copy_image"
    bl_label = "Copy Image"
    bl_options: ClassVar[set[str]] = {"UNDO_GROUPED"}  # ty: ignore[invalid-attribute-override]

    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        image = image_from_object(context.active_object)
        if image is None:
            return copy_failed(self)
        if not copy_image_to_clipboard(context, image):
            self.report({"ERROR"}, "Could not copy image to the clipboard")
            return {"CANCELLED"}
        return {"FINISHED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (
            context.area is not None
            and context.area.type == "VIEW_3D"
            and context.mode == "OBJECT"
            and image_from_object(context.active_object) is not None
        )


def view3d_copy_image_context_menu_draw(self, _context: bpy.types.Context) -> None:
    """Draw the Copy Image operator in the 3D View object context menu."""
    self.layout.separator()
    self.layout.operator(PASTY_OT_view3d_copy_image.bl_idname, icon="COPYDOWN")


# endregion


# region View3D Paste Reference Operator


class PASTY_OT_view3d_paste_reference(bpy.types.Operator):
    """Paste image from the clipboard as a reference"""

    bl_idname = "pasty.view3d_paste_reference"
    bl_label = "Paste as Reference"
    bl_options: ClassVar[set[str]] = {"UNDO_GROUPED"}  # ty: ignore[invalid-attribute-override]

    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        image = paste_image_from_clipboard(context)
        if image is None:
            return paste_failed(self)
        if not insert_image_as_reference(context, image):
            self.report({"ERROR"}, "Could not create a reference image")
            return {"CANCELLED"}
        return {"FINISHED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (
            context.area is not None
            and context.area.type == "VIEW_3D"
            and context.area.ui_type == "VIEW_3D"
            and context.mode == "OBJECT"
        )


def view3d_paste_reference_image_add_menu_draw(self, _context: bpy.types.Context) -> None:
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
    bl_options: ClassVar[set[str]] = {"UNDO_GROUPED"}  # ty: ignore[invalid-attribute-override]

    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        image = paste_image_from_clipboard(context)
        if image is None:
            return paste_failed(self)
        if not insert_image_as_reference(context, image):
            self.report({"ERROR"}, "Could not create an image plane")
            return {"CANCELLED"}
        result = bpy.ops.image.convert_to_mesh_plane(name_from="IMAGE", delete_ref=True)
        if result != {"FINISHED"}:
            self.report({"ERROR"}, "Could not convert the reference image to a mesh plane")
            return {"CANCELLED"}
        return {"FINISHED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (
            context.area is not None
            and context.area.type == "VIEW_3D"
            and context.area.ui_type == "VIEW_3D"
            and context.mode == "OBJECT"
        )


def view3d_paste_plane_image_add_menu_draw(self, _context: bpy.types.Context) -> None:
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
    bl_options: ClassVar[set[str]] = {"UNDO_GROUPED"}  # ty: ignore[invalid-attribute-override]

    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        if context.scene is None:
            self.report({"ERROR"}, "No active scene")
            return {"CANCELLED"}

        image = paste_image_from_clipboard(context)
        if image is None:
            return paste_failed(self)

        sequence_editor = context.scene.sequence_editor or context.scene.sequence_editor_create()
        strips = sequence_collection(sequence_editor)
        current_frame = context.scene.frame_current
        end_frame = current_frame + SEQUENCE_STRIP_DURATION
        try:
            channel = first_free_sequence_channel(strips, current_frame, end_frame)
        except RuntimeError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        filepath = saved_image_path(image)
        image_strip = strips.new_image(
            name=image.name, filepath=str(filepath), channel=channel, frame_start=current_frame
        )
        image_strip.frame_final_end = end_frame
        return {"FINISHED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.area is not None and context.area.type == "SEQUENCE_EDITOR"


def sequence_editor_paste_context_menu_draw(self, _context: bpy.types.Context) -> None:
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


# region Shader Editor Copy Operator


class PASTY_OT_shader_editor_copy(bpy.types.Operator):
    """Copy selected image texture to the clipboard"""

    bl_idname = "pasty.shader_editor_copy"
    bl_label = "Copy Image"
    bl_options: ClassVar[set[str]] = {"UNDO_GROUPED"}  # ty: ignore[invalid-attribute-override]

    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        image = active_shader_image(context)
        if image is None:
            return copy_failed(self)
        if not copy_image_to_clipboard(context, image):
            self.report({"ERROR"}, "Could not copy image to the clipboard")
            return {"CANCELLED"}
        return {"FINISHED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (
            context.area is not None
            and context.area.type == "NODE_EDITOR"
            and context.area.ui_type == "ShaderNodeTree"
            and active_shader_image(context) is not None
        )


def shader_editor_copy_context_menu_draw(self, _context: bpy.types.Context) -> None:
    """Draw the Copy Image operator in the Shader Editor context menu."""
    self.layout.operator(PASTY_OT_shader_editor_copy.bl_idname, icon="COPYDOWN")


# endregion


# region Shader Editor Paste Operator


class PASTY_OT_shader_editor_paste(bpy.types.Operator):
    """Paste images from the clipboard"""

    bl_idname = "pasty.shader_editor_paste"
    bl_label = "Paste from Clipboard"
    bl_options: ClassVar[set[str]] = {"UNDO_GROUPED"}  # ty: ignore[invalid-attribute-override]

    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        assert context.space_data is not None, "No Space Data found in the current context"
        assert isinstance(context.space_data, bpy.types.SpaceNodeEditor), (
            "Current space data is not a Node Editor"
        )
        assert context.space_data.edit_tree is not None, (
            "No active node tree found in the Node Editor"
        )

        image = paste_image_from_clipboard(context)
        if image is None:
            return paste_failed(self)

        node_image = context.space_data.edit_tree.nodes.new("ShaderNodeTexImage")
        location_x, location_y = context.space_data.cursor_location
        node_image.location = location_x, location_y

        node_image.image = image
        return {"FINISHED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if (
            context.area is not None
            and context.area.type == "NODE_EDITOR"
            and context.area.ui_type == "ShaderNodeTree"
        ):
            assert isinstance(context.space_data, bpy.types.SpaceNodeEditor), (
                "Current space data is not a Node Editor"
            )
            return context.space_data.edit_tree is not None
        return False


def shader_editor_paste_context_menu_draw(self, _context: bpy.types.Context) -> None:
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
    PASTY_OT_view3d_copy_image,
    PASTY_OT_view3d_paste_reference,
    PASTY_OT_view3d_paste_plane,
    PASTY_OT_sequence_editor_paste,
    PASTY_OT_shader_editor_copy,
    PASTY_OT_shader_editor_paste,
)


def register() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_object_context_menu.append(view3d_copy_image_context_menu_draw)
    bpy.types.VIEW3D_MT_image_add.append(view3d_paste_reference_image_add_menu_draw)
    bpy.types.VIEW3D_MT_image_add.append(view3d_paste_plane_image_add_menu_draw)
    bpy.types.SEQUENCER_MT_context_menu.append(sequence_editor_paste_context_menu_draw)
    bpy.types.NODE_MT_context_menu.append(shader_editor_copy_context_menu_draw)
    bpy.types.NODE_MT_context_menu.append(shader_editor_paste_context_menu_draw)
    register_keymaps()


def unregister() -> None:
    unregister_keymaps()
    bpy.types.NODE_MT_context_menu.remove(shader_editor_paste_context_menu_draw)
    bpy.types.NODE_MT_context_menu.remove(shader_editor_copy_context_menu_draw)
    bpy.types.SEQUENCER_MT_context_menu.remove(sequence_editor_paste_context_menu_draw)
    bpy.types.VIEW3D_MT_image_add.remove(view3d_paste_plane_image_add_menu_draw)
    bpy.types.VIEW3D_MT_image_add.remove(view3d_paste_reference_image_add_menu_draw)
    bpy.types.VIEW3D_MT_object_context_menu.remove(view3d_copy_image_context_menu_draw)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


addon_keymaps: list[tuple[bpy.types.KeyMap, bpy.types.KeyMapItem]] = []

keymap_functions = (
    view3d_paste_reference_image_add_menu_km,
    view3d_paste_plane_image_add_menu_km,
    sequence_editor_paste_context_menu_km,
    shader_editor_paste_context_menu_km,
)


def register_keymaps() -> None:
    if addon_keymaps:
        return

    if bpy.context.window_manager is None:
        return

    kc = bpy.context.window_manager.keyconfigs.addon
    if not kc:
        return

    for km_func in keymap_functions:
        km, kmi = km_func(kc)
        addon_keymaps.append((km, kmi))


def unregister_keymaps() -> None:
    for km, kmi in reversed(addon_keymaps):
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()


# endregion
