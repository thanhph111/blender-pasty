from importlib import util
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace

import bpy


def main() -> None:
    module = load_addon()
    expected_operator_ids = {
        "pasty.view3d_copy_image",
        "pasty.view3d_paste_reference",
        "pasty.view3d_paste_plane",
        "pasty.sequence_editor_paste",
        "pasty.shader_editor_copy",
        "pasty.shader_editor_paste",
    }
    actual_operator_ids = {operator.bl_idname for operator in module.classes}
    if actual_operator_ids != expected_operator_ids:
        msg = f"unexpected operator ids: {sorted(actual_operator_ids)}"
        raise RuntimeError(msg)

    assert_sequence_collection_is_available(module)
    assert_first_free_sequence_channel(module)
    assert_object_images_can_be_found(module)
    assert_shader_paste_replaces_selected_image_node(module)
    assert_shader_paste_links_selected_principled(module)
    assert_shader_paste_handles_multiple_images(module)
    assert_sequence_strips_can_be_added_for_multiple_images(module)
    assert_clipboard_image_file_paths_can_be_loaded(module)
    assert_generated_image_can_be_saved(module)

    module.register()
    module.unregister()


def load_addon() -> ModuleType:
    addon_path = Path(__file__).resolve().parents[1] / "__init__.py"
    spec = util.spec_from_file_location("pasty_smoke", addon_path)
    if spec is None or spec.loader is None:
        msg = f"could not load add-on from {addon_path}"
        raise RuntimeError(msg)

    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_generated_image_can_be_saved(module: ModuleType) -> None:
    image = bpy.data.images.new("pasty-test", 2, 2)
    filepath = None
    try:
        image.pixels.foreach_set([1.0, 0.0, 0.0, 1.0] * 4)
        filepath = module.saved_image_path(image)
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


def assert_sequence_collection_is_available(module: ModuleType) -> None:
    scene = bpy.context.scene
    if scene is None:
        msg = "no active scene"
        raise RuntimeError(msg)

    sequence_editor = scene.sequence_editor or scene.sequence_editor_create()
    collection = module.sequence_collection(sequence_editor)
    if not hasattr(collection, "new_image"):
        msg = "sequence collection does not support new_image"
        raise RuntimeError(msg)


def assert_first_free_sequence_channel(module: ModuleType) -> None:
    expected_channel = 2
    strips = [
        SimpleNamespace(channel=1, frame_final_start=1, frame_final_end=51),
        SimpleNamespace(channel=2, frame_final_start=60, frame_final_end=90),
    ]
    channel = module.first_free_sequence_channel(strips, frame_start=1, frame_end=51)
    if channel != expected_channel:
        msg = f"expected channel {expected_channel}, got {channel}"
        raise RuntimeError(msg)


def assert_object_images_can_be_found(module: ModuleType) -> None:
    image = bpy.data.images.new("pasty-object-test", 2, 2)
    material = bpy.data.materials.new("pasty-object-test")
    material.use_nodes = True
    obj = None
    mesh = None
    try:
        obj = bpy.data.objects.new("pasty-object-test", None)
        obj.empty_display_type = "IMAGE"
        obj.data = image
        if module.image_from_object(obj) != image:
            msg = "could not find image from empty image object"
            raise RuntimeError(msg)
        bpy.data.objects.remove(obj)

        mesh = bpy.data.meshes.new("pasty-object-test")
        obj = bpy.data.objects.new("pasty-object-test", mesh)
        node = material.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        obj.active_material = material
        if module.image_from_object(obj) != image:
            msg = "could not find image from object material"
            raise RuntimeError(msg)
    finally:
        if obj is not None:
            bpy.data.objects.remove(obj)
        if mesh is not None:
            bpy.data.meshes.remove(mesh)
        bpy.data.materials.remove(material)
        bpy.data.images.remove(image)


def assert_shader_paste_replaces_selected_image_node(module: ModuleType) -> None:
    original_image = bpy.data.images.new("pasty-original-shader-test", 2, 2)
    pasted_image = bpy.data.images.new("pasty-pasted-shader-test", 2, 2)
    material = bpy.data.materials.new("pasty-replace-shader-test")
    material.use_nodes = True
    try:
        tree = material.node_tree
        image_node = tree.nodes.new("ShaderNodeTexImage")
        image_node.image = original_image
        image_node.select = True
        tree.nodes.active = image_node
        image_node_count = len(
            [node for node in tree.nodes if node.bl_idname == "ShaderNodeTexImage"]
        )

        module.paste_image_into_shader_tree(tree, pasted_image, (40, 20))

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


def assert_shader_paste_links_selected_principled(module: ModuleType) -> None:
    image = bpy.data.images.new("pasty-link-shader-test", 2, 2)
    material = bpy.data.materials.new("pasty-link-shader-test")
    material.use_nodes = True
    try:
        tree = material.node_tree
        principled = next(
            node for node in tree.nodes if node.bl_idname == "ShaderNodeBsdfPrincipled"
        )
        for node in tree.nodes:
            node.select = False
        principled.select = True
        tree.nodes.active = principled

        module.paste_image_into_shader_tree(tree, image, (80, -60))

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


def assert_shader_paste_handles_multiple_images(module: ModuleType) -> None:
    first_image = bpy.data.images.new("pasty-multi-shader-first-test", 2, 2)
    second_image = bpy.data.images.new("pasty-multi-shader-second-test", 2, 2)
    material = bpy.data.materials.new("pasty-multi-shader-test")
    material.use_nodes = True
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
        module.paste_images_into_shader_tree(tree, images, (120, 20))

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
        if second_node.location.y != first_node.location.y - module.SHADER_NODE_VERTICAL_SPACING:
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


def assert_sequence_strips_can_be_added_for_multiple_images(module: ModuleType) -> None:
    scene = bpy.context.scene
    if scene is None:
        msg = "no active scene"
        raise RuntimeError(msg)

    with TemporaryDirectory() as temp_dir:
        first_filepath = Path(temp_dir) / "pasty first strip.png"
        second_filepath = Path(temp_dir) / "pasty second strip.png"
        save_test_image(first_filepath, "pasty-first-strip-source-test", [1.0, 0.0, 0.0, 1.0])
        save_test_image(second_filepath, "pasty-second-strip-source-test", [0.0, 0.0, 1.0, 1.0])
        first_image = module.load_image_file(first_filepath)
        second_image = module.load_image_file(second_filepath)
        added_strips = []
        try:
            if first_image is None or second_image is None:
                msg = "could not load sequence image files"
                raise RuntimeError(msg)

            sequence_editor = scene.sequence_editor or scene.sequence_editor_create()
            strips = module.sequence_collection(sequence_editor)
            added_strips = module.add_sequence_image_strips(
                strips, [first_image, second_image], frame_start=1000
            )
            if [strip.frame_final_start for strip in added_strips] != [
                1000,
                1000 + module.SEQUENCE_STRIP_DURATION,
            ]:
                msg = "multiple sequence paste did not place strips in a row"
                raise RuntimeError(msg)
            if any(strip.frame_final_end <= strip.frame_final_start for strip in added_strips):
                msg = "multiple sequence paste created an invalid frame range"
                raise RuntimeError(msg)
        finally:
            for strip in added_strips:
                strips.remove(strip)
            if second_image is not None:
                bpy.data.images.remove(second_image)
            if first_image is not None:
                bpy.data.images.remove(first_image)


def assert_clipboard_image_file_paths_can_be_loaded(module: ModuleType) -> None:
    with TemporaryDirectory() as temp_dir:
        first_filepath = Path(temp_dir) / "pasty first clipboard path.png"
        second_filepath = Path(temp_dir) / "pasty second clipboard path.png"
        save_test_image(first_filepath, "pasty-first-path-source-test", [0.0, 1.0, 0.0, 1.0])
        save_test_image(second_filepath, "pasty-second-path-source-test", [1.0, 1.0, 0.0, 1.0])

        text = f"copy\n{first_filepath.as_uri()}\n{second_filepath}\n{first_filepath}\n"
        paths = module.image_file_paths_from_clipboard_text(text)
        if paths != [first_filepath, second_filepath]:
            msg = f"unexpected clipboard image file paths: {paths}"
            raise RuntimeError(msg)

        loaded_image = module.load_image_file(first_filepath)
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


if __name__ == "__main__":
    main()
