from importlib import util
from pathlib import Path
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


if __name__ == "__main__":
    main()
