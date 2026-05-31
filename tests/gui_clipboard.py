from collections.abc import Iterator
from contextlib import contextmanager
from importlib import util
from pathlib import Path
from types import ModuleType
from typing import Literal, Protocol, cast

import bpy

AreaType = Literal["NODE_EDITOR", "SEQUENCE_EDITOR", "VIEW_3D"]


class PastyOps(Protocol):
    def view3d_paste_reference(self) -> set[str]: ...

    def view3d_paste_plane(self) -> set[str]: ...

    def sequence_editor_paste(self) -> set[str]: ...

    def shader_editor_paste(self) -> set[str]: ...


def main() -> None:
    module = load_addon()
    module.register()
    try:
        test_view3d_reference()
        test_view3d_plane()
        test_sequencer_strip()
        test_shader_node()
    finally:
        module.unregister()


def load_addon() -> ModuleType:
    addon_path = Path(__file__).resolve().parents[1] / "__init__.py"
    spec = util.spec_from_file_location("pasty_gui", addon_path)
    if spec is None or spec.loader is None:
        msg = f"could not load add-on from {addon_path}"
        raise RuntimeError(msg)

    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def editor(area_type: AreaType, ui_type: str | None = None) -> Iterator[bpy.types.Context]:
    screen = bpy.context.screen
    if screen is None:
        msg = "GUI test needs an active screen"
        raise RuntimeError(msg)

    area = screen.areas[0]
    area.type = area_type
    if ui_type is not None:
        area.ui_type = ui_type

    region = next(region for region in area.regions if region.type == "WINDOW")
    with bpy.context.temp_override(area=area, region=region):
        yield bpy.context


def test_view3d_reference() -> None:
    before = set(bpy.data.objects)
    with editor("VIEW_3D"):
        result = pasty_ops().view3d_paste_reference()

    assert_finished("view3d reference", result)
    created = set(bpy.data.objects) - before
    if not any(obj.type == "EMPTY" and obj.empty_display_type == "IMAGE" for obj in created):
        msg = "View3D reference paste did not create an image empty"
        raise RuntimeError(msg)


def test_view3d_plane() -> None:
    before = set(bpy.data.objects)
    with editor("VIEW_3D"):
        result = pasty_ops().view3d_paste_plane()

    assert_finished("view3d plane", result)
    created = set(bpy.data.objects) - before
    if not any(obj.type == "MESH" for obj in created):
        msg = "View3D plane paste did not create a mesh object"
        raise RuntimeError(msg)


def test_sequencer_strip() -> None:
    with editor("SEQUENCE_EDITOR"):
        result = pasty_ops().sequence_editor_paste()

    assert_finished("sequencer", result)
    scene = bpy.context.scene
    if scene is None:
        msg = "Sequencer paste left no active scene"
        raise RuntimeError(msg)

    sequence_editor = scene.sequence_editor
    if sequence_editor is None or not sequence_editor.strips:
        msg = "Sequencer paste did not create an image strip"
        raise RuntimeError(msg)

    pasted = [image for image in bpy.data.images if image.get("pasty.filepath")]
    if not pasted:
        msg = "Sequencer paste did not save a pasted image file"
        raise RuntimeError(msg)

    filepath = Path(pasted[-1]["pasty.filepath"])
    if not filepath.exists():
        msg = f"Sequencer pasted image file does not exist: {filepath}"
        raise RuntimeError(msg)


def test_shader_node() -> None:
    obj = bpy.context.object
    if obj is None:
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.object
    if obj is None:
        msg = "could not create an active object for the shader editor"
        raise RuntimeError(msg)

    material = bpy.data.materials.new("Pasty GUI Test")
    material.use_nodes = True
    obj.active_material = material

    before = set(material.node_tree.nodes)
    with editor("NODE_EDITOR", "ShaderNodeTree"):
        result = pasty_ops().shader_editor_paste()

    assert_finished("shader editor", result)
    created = set(material.node_tree.nodes) - before
    if not any(node.bl_idname == "ShaderNodeTexImage" and node.image for node in created):
        msg = "Shader paste did not create an image texture node"
        raise RuntimeError(msg)


def assert_finished(name: str, result: set[str]) -> None:
    if result != {"FINISHED"}:
        msg = f"{name} returned {result}"
        raise RuntimeError(msg)


def pasty_ops() -> PastyOps:
    return cast("PastyOps", getattr(bpy.ops, "pasty"))  # noqa: B009


if __name__ == "__main__":
    main()
    bpy.ops.wm.quit_blender()
