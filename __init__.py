import sys
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import gettempdir
from typing import ClassVar, Literal
from urllib.parse import unquote, urlparse

import bpy

OperatorReturn = set[Literal["RUNNING_MODAL", "CANCELLED", "FINISHED", "PASS_THROUGH", "INTERFACE"]]
SEQUENCE_STRIP_DURATION = 50
SEQUENCE_MAX_CHANNEL = 128
VIEW3D_IMAGE_OFFSET = 1.0
SHADER_NODE_VERTICAL_SPACING = 260
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

# region Image Editor Utilities


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


def paste_image_from_clipboard(context: bpy.types.Context) -> bpy.types.Image | None:
    """Paste an image from the clipboard into a new Blender image data-block."""
    images = paste_images_from_clipboard(context)
    if not images:
        return None
    return images[0]


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


def image_from_node(node) -> bpy.types.Image | None:
    if node is not None and node.bl_idname == "ShaderNodeTexImage":
        return node.image
    return None


def image_from_material(material: bpy.types.Material | None) -> bpy.types.Image | None:
    # Do not read material.use_nodes here. Blender 5.1 warns that it is going away in 6.0.
    # In newer Blender, material.node_tree is the useful check.
    if material is None or material.node_tree is None:
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
        # Image reference objects store their image directly on object.data.
        if isinstance(obj.data, bpy.types.Image):
            return obj.data
        return None

    # Mesh objects do not own images directly; look through their active material.
    return image_from_material(obj.active_material)


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


def offset_shader_node_location(location, offset_index: int) -> tuple[float, float]:
    location_x, location_y = location
    return location_x, location_y - (offset_index * SHADER_NODE_VERTICAL_SPACING)


def add_shader_image_node(node_tree, image: bpy.types.Image, location, offset_index: int = 0):
    image_node = node_tree.nodes.new("ShaderNodeTexImage")
    image_node.location = offset_shader_node_location(location, offset_index)
    image_node.image = image
    return image_node


def paste_image_into_shader_tree(node_tree, image: bpy.types.Image, location) -> None:
    paste_images_into_shader_tree(node_tree, [image], location)


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


def image_display_name(image: bpy.types.Image) -> str:
    return bpy.path.display_name(image.name, title_case=False)


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
    reference_object.name = image_display_name(image)
    reference_object.data = image  # ty: ignore[invalid-assignment]
    reference_object.location.x += offset_index * VIEW3D_IMAGE_OFFSET
    return True


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


# endregion


# region View3D Paste Reference Operator


class PASTY_OT_view3d_paste_reference(bpy.types.Operator):
    """Paste image from the clipboard as a reference"""

    bl_idname = "pasty.view3d_paste_reference"
    bl_label = "Paste as Reference"
    bl_options: ClassVar[set[str]] = {"UNDO_GROUPED"}  # ty: ignore[invalid-attribute-override]

    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        images = paste_images_from_clipboard(context)
        if not images:
            return paste_failed(self)
        for offset_index, image in enumerate(images):
            if not insert_image_as_reference(context, image, offset_index):
                self.report({"ERROR"}, "Could not create a reference image")
                return {"CANCELLED"}
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
        images = paste_images_from_clipboard(context)
        if not images:
            return paste_failed(self)
        for offset_index, image in enumerate(images):
            if not insert_image_as_reference(context, image, offset_index):
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

        images = paste_images_from_clipboard(context)
        if not images:
            return paste_failed(self)

        paste_images_into_shader_tree(
            context.space_data.edit_tree, images, context.space_data.cursor_location
        )
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
        # Headless Blender has no window manager. CI still needs register() to succeed.
        return

    kc = bpy.context.window_manager.keyconfigs.addon
    if not kc:
        # Some startup states have no add-on keyconfig yet.
        return

    for km_func in keymap_functions:
        km, kmi = km_func(kc)
        addon_keymaps.append((km, kmi))


def unregister_keymaps() -> None:
    # Track only keymaps we created so reload/unregister does not touch user shortcuts.
    for km, kmi in reversed(addon_keymaps):
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()


# endregion
