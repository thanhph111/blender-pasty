from typing import ClassVar

import bpy

from ..blender_types import OperatorReturn
from ..clipboard import (
    copy_failed,
    copy_image_to_clipboard,
    paste_failed,
    paste_images_from_clipboard,
)
from ..image_lookup import image_from_node
from ..storage import TEMP_FOLDER_WARNING, prepare_images_for_blender_data

SHADER_NODE_VERTICAL_SPACING = 260


def active_shader_image(context: bpy.types.Context) -> bpy.types.Image | None:
    if context.space_data is None or not isinstance(context.space_data, bpy.types.SpaceNodeEditor):
        return None
    if context.space_data.edit_tree is None:
        return None

    nodes = context.space_data.edit_tree.nodes
    # Active node first matches the thing Blender shows as the user's focused node.
    active_image = image_from_node(nodes.active)
    if active_image is not None:
        return active_image

    for node in nodes:
        if node.select:
            image = image_from_node(node)
            if image is not None:
                return image

    return None


def active_or_selected_node(nodes, bl_idname: str):
    # Prefer the active node when it matches; selection can contain several nodes.
    active_node = nodes.active
    if active_node is not None and active_node.bl_idname == bl_idname:
        return active_node

    for node in nodes:
        if node.select and node.bl_idname == bl_idname:
            return node

    return None


def link_image_to_principled_base_color(node_tree, image_node, principled_node) -> None:
    base_color = principled_node.inputs.get("Base Color")
    color = image_node.outputs.get("Color")
    if base_color is None or color is None:
        return

    for link in list(node_tree.links):
        if link.to_socket == base_color:
            node_tree.links.remove(link)

    # Blender's Python API names this as input first, then output.
    node_tree.links.new(base_color, color)


def add_shader_image_node(node_tree, image: bpy.types.Image, location, offset_index: int = 0):
    image_node = node_tree.nodes.new("ShaderNodeTexImage")
    location_x, location_y = location
    image_node.location = location_x, location_y - (offset_index * SHADER_NODE_VERTICAL_SPACING)
    image_node.image = image
    return image_node


def paste_images_into_shader_tree(node_tree, images: list[bpy.types.Image], location) -> None:
    if not images:
        return

    nodes = node_tree.nodes
    image_node = active_or_selected_node(nodes, "ShaderNodeTexImage")
    if image_node is not None:
        # Replacing a selected image node is less destructive than adding a duplicate.
        image_node.image = images[0]
        for offset_index, image in enumerate(images[1:], start=1):
            add_shader_image_node(node_tree, image, image_node.location, offset_index)
        return

    principled_node = active_or_selected_node(nodes, "ShaderNodeBsdfPrincipled")
    for offset_index, image in enumerate(images):
        image_node = add_shader_image_node(node_tree, image, location, offset_index)
        if offset_index == 0 and principled_node is not None:
            # Multiple paste creates many image nodes, but only the first should auto-link.
            link_image_to_principled_base_color(node_tree, image_node, principled_node)


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
        # Copy poll may inspect the active node, but it still avoids touching the system clipboard.
        return (
            context.area is not None
            and context.area.type == "NODE_EDITOR"
            and context.area.ui_type == "ShaderNodeTree"
            and active_shader_image(context) is not None
        )


def shader_editor_copy_context_menu_draw(self, _context: bpy.types.Context) -> None:
    """Draw the Copy Image operator in the Shader Editor context menu."""
    self.layout.operator(PASTY_OT_shader_editor_copy.bl_idname, icon="COPYDOWN")


class PASTY_OT_shader_editor_paste(bpy.types.Operator):
    """Paste images from the clipboard"""

    bl_idname = "pasty.shader_editor_paste"
    bl_label = "Paste Image Texture"
    bl_options: ClassVar[set[str]] = {"UNDO_GROUPED"}  # ty: ignore[invalid-attribute-override]

    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        assert context.space_data is not None, "No Space Data found in the current context"
        assert isinstance(context.space_data, bpy.types.SpaceNodeEditor), (
            "Current space data is not a Node Editor"
        )
        assert context.space_data.edit_tree is not None, (
            "No active node tree found in the Node Editor"
        )

        pasted_images = paste_images_from_clipboard(context)
        if not pasted_images:
            return paste_failed(self)

        prepared = prepare_images_for_blender_data(pasted_images)
        paste_images_into_shader_tree(
            context.space_data.edit_tree, prepared.images, context.space_data.cursor_location
        )
        if prepared.used_temp_folder:
            self.report({"WARNING"}, TEMP_FOLDER_WARNING)
        return {"FINISHED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Keep poll cheap. Blender calls it while drawing UI, so do not inspect the clipboard.
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
    """Draw the Paste operator in the Shader Editor context menu."""
    self.layout.operator(PASTY_OT_shader_editor_paste.bl_idname, icon="FILE_IMAGE")


classes = (PASTY_OT_shader_editor_copy, PASTY_OT_shader_editor_paste)

menu_hooks = (
    (bpy.types.NODE_MT_context_menu, shader_editor_copy_context_menu_draw),
    (bpy.types.NODE_MT_context_menu, shader_editor_paste_context_menu_draw),
)

keymap_specs = (
    (
        "Node Editor",
        "NODE_EDITOR",
        PASTY_OT_shader_editor_paste.bl_idname,
        {"ctrl": True, "shift": True},
    ),
)
