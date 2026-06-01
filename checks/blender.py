import importlib
import sys
from importlib import util
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace

import bpy


def run_smoke_checks(module: ModuleType, *, register_addon: bool) -> None:
    modules = addon_modules(module)
    checks = (
        check_operator_ids,
        check_sequence_collection_is_available,
        check_first_free_sequence_channel,
        check_object_images_can_be_found,
        check_pasted_plane_uses_image_name,
        check_shader_paste_replaces_selected_image_node,
        check_shader_paste_links_selected_principled,
        check_shader_paste_handles_multiple_images,
        check_sequence_strips_can_be_added_for_multiple_images,
        check_clipboard_image_file_paths_can_be_loaded,
        check_clipboard_poll_failure_falls_back_to_paths,
        check_generated_image_can_be_saved,
    )
    for check in checks:
        check(modules)

    if register_addon:
        module.register()
        module.unregister()


def addon_modules(module: ModuleType) -> SimpleNamespace:
    package_name = module.__package__ or module.__name__
    implementation_name = f"{package_name}.addon"
    return SimpleNamespace(
        root=module,
        clipboard=importlib.import_module(f"{implementation_name}.clipboard"),
        image_lookup=importlib.import_module(f"{implementation_name}.image_lookup"),
        registration=importlib.import_module(f"{implementation_name}.registration"),
        sequencer=importlib.import_module(f"{implementation_name}.areas.sequencer"),
        shader_editor=importlib.import_module(f"{implementation_name}.areas.shader_editor"),
        view_3d=importlib.import_module(f"{implementation_name}.areas.view_3d"),
    )


def check_operator_ids(modules: SimpleNamespace) -> None:
    # This keeps the add-on's public operator surface deliberate.
    expected_operator_ids = {
        "pasty.view3d_copy_image",
        "pasty.view3d_paste_reference",
        "pasty.view3d_paste_plane",
        "pasty.sequence_editor_paste",
        "pasty.shader_editor_copy",
        "pasty.shader_editor_paste",
    }
    actual_operator_ids = {operator.bl_idname for operator in modules.registration.classes}
    if actual_operator_ids != expected_operator_ids:
        msg = f"unexpected operator ids: {sorted(actual_operator_ids)}"
        raise RuntimeError(msg)


def load_repo_addon() -> ModuleType:
    addon_dir = Path(__file__).resolve().parents[1]
    addon_path = addon_dir / "__init__.py"
    # Load the source package directly so smoke tests do not depend on a Blender install step.
    spec = util.spec_from_file_location(
        "pasty_smoke", addon_path, submodule_search_locations=[str(addon_dir)]
    )
    if spec is None or spec.loader is None:
        msg = f"could not load add-on from {addon_path}"
        raise RuntimeError(msg)

    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check_generated_image_can_be_saved(modules: SimpleNamespace) -> None:
    image = bpy.data.images.new("pasty-test", 2, 2)
    filepath = None
    try:
        image.pixels.foreach_set([1.0, 0.0, 0.0, 1.0] * 4)
        filepath = modules.sequencer.saved_image_path(image)
        if not filepath.exists():
            msg = f"saved image path was not created: {filepath}"
            raise RuntimeError(msg)
        if image.get("pasty.filepath") != str(filepath):
            msg = "saved image path was not stamped on the image"
            raise RuntimeError(msg)
    finally:
        if filepath is not None:
            filepath.unlink(missing_ok=True)
        bpy.data.images.remove(image)


def save_test_image(filepath: Path, name: str, color: list[float]) -> None:
    image = bpy.data.images.new(name, 2, 2)
    try:
        image.pixels.foreach_set(color * 4)
        image.save_render(str(filepath))
    finally:
        bpy.data.images.remove(image)


def ensure_material_nodes(material: bpy.types.Material) -> None:
    if material.node_tree is None:
        # Blender 4.2 may still need this. Blender 5.1 already creates node trees.
        material.use_nodes = True


def check_sequence_collection_is_available(modules: SimpleNamespace) -> None:
    scene = bpy.context.scene
    if scene is None:
        msg = "no active scene"
        raise RuntimeError(msg)

    sequence_editor = scene.sequence_editor or scene.sequence_editor_create()
    collection = modules.sequencer.sequence_collection(sequence_editor)
    if not hasattr(collection, "new_image"):
        msg = "sequence collection does not support new_image"
        raise RuntimeError(msg)


def check_first_free_sequence_channel(modules: SimpleNamespace) -> None:
    expected_channel = 2
    strips = [
        SimpleNamespace(channel=1, left_handle=1, right_handle=51),
        SimpleNamespace(channel=2, left_handle=60, right_handle=90),
    ]
    channel = modules.sequencer.first_free_sequence_channel(strips, frame_start=1, frame_end=51)
    if channel != expected_channel:
        msg = f"expected channel {expected_channel}, got {channel}"
        raise RuntimeError(msg)

    legacy_strips = [SimpleNamespace(channel=1, frame_final_start=1, frame_final_end=51)]
    # Keep this old-shape test while Blender 4.2 is the minimum supported version.
    channel = modules.sequencer.first_free_sequence_channel(
        legacy_strips, frame_start=1, frame_end=51
    )
    if channel != expected_channel:
        msg = f"expected legacy channel {expected_channel}, got {channel}"
        raise RuntimeError(msg)


def check_object_images_can_be_found(modules: SimpleNamespace) -> None:
    image = bpy.data.images.new("pasty-object-test", 2, 2)
    material = bpy.data.materials.new("pasty-object-test")
    ensure_material_nodes(material)
    empty_object = None
    mesh_object = None
    mesh = None
    try:
        empty_object = bpy.data.objects.new("pasty-object-test", None)
        empty_object.empty_display_type = "IMAGE"
        empty_object.data = image
        if modules.image_lookup.image_from_object(empty_object) != image:
            msg = "could not find image from empty image object"
            raise RuntimeError(msg)
        bpy.data.objects.remove(empty_object)
        empty_object = None

        mesh = bpy.data.meshes.new("pasty-object-test")
        mesh_object = bpy.data.objects.new("pasty-object-test", mesh)
        node = material.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        mesh_object.active_material = material
        if modules.image_lookup.image_from_object(mesh_object) != image:
            msg = "could not find image from object material"
            raise RuntimeError(msg)
    finally:
        if mesh_object is not None:
            bpy.data.objects.remove(mesh_object)
        if empty_object is not None:
            bpy.data.objects.remove(empty_object)
        if mesh is not None:
            bpy.data.meshes.remove(mesh)
        bpy.data.materials.remove(material)
        bpy.data.images.remove(image)


def check_pasted_plane_uses_image_name(modules: SimpleNamespace) -> None:
    image = bpy.data.images.new("real-image-name.png", 2, 2)
    objects_before = set(bpy.data.objects)
    try:
        if not modules.view_3d.insert_image_as_reference(bpy.context, image):
            msg = "could not create reference image"
            raise RuntimeError(msg)

        # Blender's converter keeps the reference object name when delete_ref=True.
        # This test protects the earlier reference naming step.
        result = bpy.ops.image.convert_to_mesh_plane(name_from="IMAGE", delete_ref=True)
        if result != {"FINISHED"}:
            msg = f"could not convert reference image to mesh plane: {result}"
            raise RuntimeError(msg)

        mesh_planes = [
            obj for obj in bpy.data.objects if obj not in objects_before and obj.type == "MESH"
        ]
        if not mesh_planes:
            msg = "image reference conversion did not create a mesh plane"
            raise RuntimeError(msg)
        if mesh_planes[0].name.removesuffix(".001") != "real-image-name":
            msg = f"expected pasted plane to use image name, got {mesh_planes[0].name}"
            raise RuntimeError(msg)
    finally:
        for obj in list(bpy.data.objects):
            if obj not in objects_before:
                bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.images.remove(image)


def check_shader_paste_replaces_selected_image_node(modules: SimpleNamespace) -> None:
    original_image = bpy.data.images.new("pasty-original-shader-test", 2, 2)
    pasted_image = bpy.data.images.new("pasty-pasted-shader-test", 2, 2)
    material = bpy.data.materials.new("pasty-replace-shader-test")
    ensure_material_nodes(material)
    try:
        tree = material.node_tree
        image_node = tree.nodes.new("ShaderNodeTexImage")
        image_node.image = original_image
        image_node.select = True
        tree.nodes.active = image_node
        image_node_count = len(
            [node for node in tree.nodes if node.bl_idname == "ShaderNodeTexImage"]
        )

        modules.shader_editor.paste_images_into_shader_tree(tree, [pasted_image], (40, 20))

        if image_node.image != pasted_image:
            msg = "shader paste did not replace the selected image texture"
            raise RuntimeError(msg)
        if (
            len([node for node in tree.nodes if node.bl_idname == "ShaderNodeTexImage"])
            != image_node_count
        ):
            msg = "shader paste created a new image texture instead of replacing the selected one"
            raise RuntimeError(msg)
    finally:
        bpy.data.materials.remove(material)
        bpy.data.images.remove(pasted_image)
        bpy.data.images.remove(original_image)


def check_shader_paste_links_selected_principled(modules: SimpleNamespace) -> None:
    image = bpy.data.images.new("pasty-link-shader-test", 2, 2)
    material = bpy.data.materials.new("pasty-link-shader-test")
    ensure_material_nodes(material)
    try:
        tree = material.node_tree
        principled = next(
            node for node in tree.nodes if node.bl_idname == "ShaderNodeBsdfPrincipled"
        )
        for node in tree.nodes:
            node.select = False
        principled.select = True
        tree.nodes.active = principled

        modules.shader_editor.paste_images_into_shader_tree(tree, [image], (80, -60))

        image_nodes = [node for node in tree.nodes if node.bl_idname == "ShaderNodeTexImage"]
        pasted_node = next(node for node in image_nodes if node.image == image)
        base_color = principled.inputs.get("Base Color")
        color = pasted_node.outputs.get("Color")
        if base_color is None or color is None:
            msg = "shader nodes did not expose expected image color and base color sockets"
            raise RuntimeError(msg)
        if not any(
            link.from_socket == color and link.to_socket == base_color for link in tree.links
        ):
            msg = "shader paste did not link image color to Principled Base Color"
            raise RuntimeError(msg)
    finally:
        bpy.data.materials.remove(material)
        bpy.data.images.remove(image)


def check_shader_paste_handles_multiple_images(modules: SimpleNamespace) -> None:
    first_image = bpy.data.images.new("pasty-multi-shader-first-test", 2, 2)
    second_image = bpy.data.images.new("pasty-multi-shader-second-test", 2, 2)
    material = bpy.data.materials.new("pasty-multi-shader-test")
    ensure_material_nodes(material)
    try:
        tree = material.node_tree
        principled = next(
            node for node in tree.nodes if node.bl_idname == "ShaderNodeBsdfPrincipled"
        )
        for node in tree.nodes:
            node.select = False
        principled.select = True
        tree.nodes.active = principled

        images = [first_image, second_image]
        modules.shader_editor.paste_images_into_shader_tree(tree, images, (120, 20))

        image_nodes = [
            node
            for node in tree.nodes
            if node.bl_idname == "ShaderNodeTexImage" and node.image in images
        ]
        if len(image_nodes) != len(images):
            msg = f"expected two pasted shader image nodes, got {len(image_nodes)}"
            raise RuntimeError(msg)

        first_node = next(node for node in image_nodes if node.image == first_image)
        second_node = next(node for node in image_nodes if node.image == second_image)
        expected_y = first_node.location.y - modules.shader_editor.SHADER_NODE_VERTICAL_SPACING
        if second_node.location.y != expected_y:
            msg = "multiple shader paste did not offset the second image node"
            raise RuntimeError(msg)

        base_color = principled.inputs.get("Base Color")
        color = first_node.outputs.get("Color")
        if not any(
            link.from_socket == color and link.to_socket == base_color for link in tree.links
        ):
            msg = "multiple shader paste did not link the first image"
            raise RuntimeError(msg)
    finally:
        bpy.data.materials.remove(material)
        bpy.data.images.remove(second_image)
        bpy.data.images.remove(first_image)


def check_sequence_strips_can_be_added_for_multiple_images(modules: SimpleNamespace) -> None:
    scene = bpy.context.scene
    if scene is None:
        msg = "no active scene"
        raise RuntimeError(msg)

    with TemporaryDirectory() as temp_dir:
        first_filepath = Path(temp_dir) / "pasty first strip.png"
        second_filepath = Path(temp_dir) / "pasty second strip.png"
        save_test_image(first_filepath, "pasty-first-strip-source-test", [1.0, 0.0, 0.0, 1.0])
        save_test_image(second_filepath, "pasty-second-strip-source-test", [0.0, 0.0, 1.0, 1.0])
        first_image = modules.clipboard.load_image_file(first_filepath)
        second_image = modules.clipboard.load_image_file(second_filepath)
        strips = None
        added_strips = []
        try:
            if first_image is None or second_image is None:
                msg = "could not load sequence image files"
                raise RuntimeError(msg)

            sequence_editor = scene.sequence_editor or scene.sequence_editor_create()
            strips = modules.sequencer.sequence_collection(sequence_editor)
            added_strips = modules.sequencer.add_sequence_image_strips(
                strips, [first_image, second_image], frame_start=1000
            )
            if [modules.sequencer.sequence_strip_start(strip) for strip in added_strips] != [
                1000,
                1000 + modules.sequencer.SEQUENCE_STRIP_DURATION,
            ]:
                msg = "multiple sequence paste did not place strips in a row"
                raise RuntimeError(msg)
            if any(
                modules.sequencer.sequence_strip_end(strip)
                <= modules.sequencer.sequence_strip_start(strip)
                for strip in added_strips
            ):
                msg = "multiple sequence paste created an invalid frame range"
                raise RuntimeError(msg)
        finally:
            if strips is not None:
                for strip in added_strips:
                    strips.remove(strip)
            if second_image is not None:
                bpy.data.images.remove(second_image)
            if first_image is not None:
                bpy.data.images.remove(first_image)


def check_clipboard_image_file_paths_can_be_loaded(modules: SimpleNamespace) -> None:
    with TemporaryDirectory() as temp_dir:
        first_filepath = Path(temp_dir) / "pasty first clipboard path.png"
        second_filepath = Path(temp_dir) / "pasty second clipboard path.png"
        save_test_image(first_filepath, "pasty-first-path-source-test", [0.0, 1.0, 0.0, 1.0])
        save_test_image(second_filepath, "pasty-second-path-source-test", [1.0, 1.0, 0.0, 1.0])

        text = f"copy\n{first_filepath.as_uri()}\n{second_filepath}\n{first_filepath}\n"
        paths = modules.clipboard.image_file_paths_from_clipboard_text(text)
        if paths != [first_filepath, second_filepath]:
            msg = f"unexpected clipboard image file paths: {paths}"
            raise RuntimeError(msg)

        loaded_image = modules.clipboard.load_image_file(first_filepath)
        try:
            if loaded_image is None:
                msg = "could not load clipboard image file"
                raise RuntimeError(msg)
            if loaded_image.get("pasty.source_path") != str(first_filepath):
                msg = "loaded clipboard image file was not stamped with its source path"
                raise RuntimeError(msg)
        finally:
            if loaded_image is not None:
                bpy.data.images.remove(loaded_image)


def check_clipboard_poll_failure_falls_back_to_paths(modules: SimpleNamespace) -> None:
    with TemporaryDirectory() as temp_dir:
        filepath = Path(temp_dir) / "pasty fallback path.png"
        save_test_image(filepath, "pasty-fallback-path-source-test", [0.0, 1.0, 1.0, 1.0])

        original_clipboard_paste = modules.clipboard.image_clipboard_paste_result
        fake_context = SimpleNamespace(
            area=SimpleNamespace(type="VIEW_3D", ui_type="VIEW_3D"),
            window_manager=SimpleNamespace(clipboard=str(filepath)),
        )

        try:
            # Simulate Blender's image clipboard poll failure without needing a real GUI clipboard.
            modules.clipboard.image_clipboard_paste_result = clipboard_paste_poll_failed
            images = modules.clipboard.paste_images_from_clipboard(fake_context)
            try:
                if len(images) != 1:
                    msg = f"expected one fallback image, got {len(images)}"
                    raise RuntimeError(msg)
                if images[0].get("pasty.source_path") != str(filepath):
                    msg = "fallback image was not loaded from the clipboard path"
                    raise RuntimeError(msg)
            finally:
                for image in images:
                    bpy.data.images.remove(image)
        finally:
            modules.clipboard.image_clipboard_paste_result = original_clipboard_paste


def clipboard_paste_poll_failed() -> None:
    return None
