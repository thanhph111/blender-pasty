from importlib import util
from pathlib import Path
from types import ModuleType

import bpy


def main() -> None:
    module = load_addon()
    expected_operator_ids = {
        "pasty.view3d_paste_reference",
        "pasty.view3d_paste_plane",
        "pasty.sequence_editor_paste",
        "pasty.shader_editor_paste",
    }
    actual_operator_ids = {operator.bl_idname for operator in module.classes}
    if actual_operator_ids != expected_operator_ids:
        msg = f"unexpected operator ids: {sorted(actual_operator_ids)}"
        raise RuntimeError(msg)

    assert_sequence_collection_is_available(module)
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


if __name__ == "__main__":
    main()
