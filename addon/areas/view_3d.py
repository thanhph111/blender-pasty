from typing import ClassVar

import bpy

from ..blender_types import OperatorReturn
from ..clipboard import (
    copy_failed,
    copy_image_to_clipboard,
    paste_failed,
    paste_images_from_clipboard,
)
from ..image_lookup import image_from_object
from ..storage import TEMP_FOLDER_WARNING, prepare_images_for_blender_data

VIEW3D_IMAGE_OFFSET = 1.0


def insert_image_as_reference(
    context: bpy.types.Context, image: bpy.types.Image, offset_index: int = 0
) -> bool:
    """Insert a pasted image as a reference object in the 3D View."""
    bpy.ops.object.empty_add(type="IMAGE", radius=5.0, align="VIEW")
    if context.active_object is None:
        return False

    reference_object = context.active_object
    # convert_to_mesh_plane(delete_ref=True) keeps the reference object's name.
    # Name it from the image now, or pasted planes become "Empty".
    reference_object.name = bpy.path.display_name(image.name, title_case=False)
    reference_object.data = image  # ty: ignore[invalid-assignment]
    reference_object.location.x += offset_index * VIEW3D_IMAGE_OFFSET
    return True


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
        # Keep poll cheap. Blender calls it while drawing UI, so do not inspect the clipboard.
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


class PASTY_OT_view3d_paste_reference(bpy.types.Operator):
    """Paste image from the clipboard as a reference"""

    bl_idname = "pasty.view3d_paste_reference"
    bl_label = "Paste as Reference"
    bl_options: ClassVar[set[str]] = {"UNDO_GROUPED"}  # ty: ignore[invalid-attribute-override]

    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        pasted_images = paste_images_from_clipboard(context)
        if not pasted_images:
            return paste_failed(self)
        prepared = prepare_images_for_blender_data(pasted_images)
        for offset_index, image in enumerate(prepared.images):
            if not insert_image_as_reference(context, image, offset_index):
                self.report({"ERROR"}, "Could not create a reference image")
                return {"CANCELLED"}
        if prepared.used_temp_folder:
            self.report({"WARNING"}, TEMP_FOLDER_WARNING)
        return {"FINISHED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Keep poll cheap. Blender calls it while drawing UI, so do not inspect the clipboard.
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


class PASTY_OT_view3d_paste_plane(bpy.types.Operator):
    """Paste image from the clipboard as a plane"""

    bl_idname = "pasty.view3d_paste_plane"
    bl_label = "Paste as Plane"
    bl_options: ClassVar[set[str]] = {"UNDO_GROUPED"}  # ty: ignore[invalid-attribute-override]

    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        pasted_images = paste_images_from_clipboard(context)
        if not pasted_images:
            return paste_failed(self)
        prepared = prepare_images_for_blender_data(pasted_images)
        for offset_index, image in enumerate(prepared.images):
            if not insert_image_as_reference(context, image, offset_index):
                self.report({"ERROR"}, "Could not create an image plane")
                return {"CANCELLED"}
            result = bpy.ops.image.convert_to_mesh_plane(name_from="IMAGE", delete_ref=True)
            if result != {"FINISHED"}:
                self.report({"ERROR"}, "Could not convert the reference image to a mesh plane")
                return {"CANCELLED"}
        if prepared.used_temp_folder:
            self.report({"WARNING"}, TEMP_FOLDER_WARNING)
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
    """Draw the Paste as Plane operator in the 3D View Add Image menu."""
    self.layout.operator(PASTY_OT_view3d_paste_plane.bl_idname, icon="FILE_IMAGE")


classes = (PASTY_OT_view3d_copy_image, PASTY_OT_view3d_paste_reference, PASTY_OT_view3d_paste_plane)

menu_hooks = (
    (bpy.types.VIEW3D_MT_object_context_menu, view3d_copy_image_context_menu_draw),
    (bpy.types.VIEW3D_MT_image_add, view3d_paste_reference_image_add_menu_draw),
    (bpy.types.VIEW3D_MT_image_add, view3d_paste_plane_image_add_menu_draw),
)

keymap_specs = (
    (
        "3D View",
        "VIEW_3D",
        PASTY_OT_view3d_paste_reference.bl_idname,
        {"ctrl": True, "shift": True, "alt": True},
    ),
    ("3D View", "VIEW_3D", PASTY_OT_view3d_paste_plane.bl_idname, {"ctrl": True, "shift": True}),
)
