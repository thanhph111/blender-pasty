import importlib
import sys
from datetime import datetime, timedelta, timezone
from importlib import util
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING, cast

import bpy

if TYPE_CHECKING:
    from collections.abc import Iterable

MISSING_BLENDER_ATTR = object()


def run_blender_checks(module: ModuleType, *, register_addon: bool) -> None:
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
        check_blender_relative_clipboard_paths_can_be_loaded,
        check_platform_clipboard_file_paths_can_be_loaded,
        check_clipboard_poll_failure_falls_back_to_paths,
        check_linux_clipboard_tool_hint_is_shown_when_needed,
        check_linux_clipboard_tools_follow_session,
        check_linux_clipboard_image_fallback_can_be_loaded,
        check_linux_clipboard_copy_fallback_writes_png,
        check_clipboard_images_can_be_packed,
        check_generated_image_can_be_saved,
        check_generated_filenames_follow_preferences,
        check_unique_paths_do_not_overwrite,
        check_gather_updates_images_and_sequence_strips,
        check_managed_copy_stays_in_current_folder,
    )
    for check in checks:
        check(modules)

    if register_addon:
        check_registration_cycles(module, modules)


def addon_modules(module: ModuleType) -> SimpleNamespace:
    package_name = module.__package__ or module.__name__
    implementation_name = f"{package_name}.addon"
    return SimpleNamespace(
        root=module,
        clipboard=importlib.import_module(f"{implementation_name}.clipboard"),
        image_lookup=importlib.import_module(f"{implementation_name}.image_lookup"),
        preferences=importlib.import_module(f"{implementation_name}.preferences"),
        registration=importlib.import_module(f"{implementation_name}.registration"),
        storage=importlib.import_module(f"{implementation_name}.storage"),
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
        "pasty.gather_pasted_images",
    }
    actual_operator_ids = {
        operator.bl_idname
        for operator in modules.registration.classes
        if issubclass(operator, bpy.types.Operator)
    }
    if actual_operator_ids != expected_operator_ids:
        msg = f"unexpected operator ids: {sorted(actual_operator_ids)}"
        raise RuntimeError(msg)


def check_registration_cycles(module: ModuleType, modules: SimpleNamespace) -> None:
    # Blender reloads add-ons during development. Two full cycles catch the common
    # mistakes: classes, menu entries, or shortcuts that are not removed.
    menu_counts_before = menu_hook_counts(modules)
    keymap_counts_before = keymap_item_counts(modules)

    for _ in range(2):
        module.register()
        try:
            assert_class_registration_state(modules, expected=True)
            assert_menu_hook_counts(modules, menu_counts_before, expected_delta=1)
            assert_keymap_item_counts(modules, keymap_counts_before, expected_delta=1)
        finally:
            module.unregister()

        assert_class_registration_state(modules, expected=False)
        assert_menu_hook_counts(modules, menu_counts_before, expected_delta=0)
        assert_keymap_item_counts(modules, keymap_counts_before, expected_delta=0)
        if modules.registration.addon_keymaps:
            msg = "unregister left Pasty keymaps behind"
            raise RuntimeError(msg)


def assert_class_registration_state(modules: SimpleNamespace, *, expected: bool) -> None:
    mismatched = [
        cls.__name__
        for cls in modules.registration.classes
        if bool(getattr(cls, "is_registered", False)) != expected
    ]
    if mismatched:
        state = "registered" if expected else "unregistered"
        msg = f"expected Pasty classes to be {state}: {mismatched}"
        raise RuntimeError(msg)


def menu_hook_counts(modules: SimpleNamespace) -> dict[tuple[object, object], int]:
    return {
        (menu, draw): menu_draw_functions(menu).count(draw)
        for menu, draw in modules.registration.menu_hooks
    }


def assert_menu_hook_counts(
    modules: SimpleNamespace,
    counts_before: dict[tuple[object, object], int],
    *,
    expected_delta: int,
) -> None:
    for menu, draw in modules.registration.menu_hooks:
        expected_count = counts_before[(menu, draw)] + expected_delta
        actual_count = menu_draw_functions(menu).count(draw)
        if actual_count != expected_count:
            msg = (
                f"expected {draw.__name__} on {menu.__name__} "
                f"{expected_count} time(s), got {actual_count}"
            )
            raise RuntimeError(msg)


def menu_draw_functions(menu: object) -> list[object]:
    draw = blender_attr(menu, "draw")
    draw_functions = blender_attr(draw, "_draw_funcs", ())
    return list(cast("Iterable[object]", draw_functions))


def keymap_item_counts(modules: SimpleNamespace) -> dict[tuple[object, ...], int]:
    return {
        spec_key(spec): len(matching_keymap_items(spec))
        for spec in modules.registration.keymap_specs
    }


def assert_keymap_item_counts(
    modules: SimpleNamespace, counts_before: dict[tuple[object, ...], int], *, expected_delta: int
) -> None:
    if addon_keyconfig() is None:
        if modules.registration.addon_keymaps:
            msg = "Pasty tracked keymaps even though Blender has no add-on keyconfig"
            raise RuntimeError(msg)
        return

    for spec in modules.registration.keymap_specs:
        key = spec_key(spec)
        expected_count = counts_before[key] + expected_delta
        actual_count = len(matching_keymap_items(spec))
        if actual_count != expected_count:
            keymap_name, _space_type, operator_id, _modifiers = spec
            msg = (
                f"expected {operator_id} shortcut in {keymap_name} "
                f"{expected_count} time(s), got {actual_count}"
            )
            raise RuntimeError(msg)


def spec_key(spec: tuple[object, ...]) -> tuple[object, ...]:
    keymap_name, space_type, operator_id, modifiers_object = spec
    modifiers = cast("dict[str, bool]", modifiers_object)
    return keymap_name, space_type, operator_id, tuple(sorted(modifiers.items()))


def matching_keymap_items(spec: tuple[object, ...]) -> list[object]:
    keyconfig = addon_keyconfig()
    if keyconfig is None:
        return []

    keymap_name, space_type, operator_id, modifiers_object = spec
    modifiers = cast("dict[str, bool]", modifiers_object)
    matches = []
    keymaps = cast("Iterable[object]", blender_attr(keyconfig, "keymaps"))
    for keymap in keymaps:
        if (
            blender_attr(keymap, "name") != keymap_name
            or blender_attr(keymap, "space_type") != space_type
        ):
            continue
        keymap_items = cast("Iterable[object]", blender_attr(keymap, "keymap_items"))
        matches.extend(
            keymap_item
            for keymap_item in keymap_items
            if (
                blender_attr(keymap_item, "idname") == operator_id
                and blender_attr(keymap_item, "type") == "V"
                and blender_attr(keymap_item, "value") == "PRESS"
                and all(getattr(keymap_item, name) == value for name, value in modifiers.items())
            )
        )
    return matches


def blender_attr(obj: object, name: str, default: object = MISSING_BLENDER_ATTR) -> object:
    # fake-bpy cannot type every runtime Blender collection. Keep that dynamic
    # boundary here so the cleanup checks can still assert real Blender state.
    if default is MISSING_BLENDER_ATTR:
        return getattr(obj, name)
    return getattr(obj, name, default)


def addon_keyconfig() -> object | None:
    if bpy.context.window_manager is None:
        return None
    return bpy.context.window_manager.keyconfigs.addon


def load_repo_addon() -> ModuleType:
    addon_dir = Path(__file__).resolve().parents[1]
    addon_path = addon_dir / "__init__.py"
    # Load the source package directly so source add-on checks do not depend on
    # a Blender install step.
    spec = util.spec_from_file_location(
        "pasty_check", addon_path, submodule_search_locations=[str(addon_dir)]
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
        pasted_image = modules.clipboard.PastedImage(image, modules.storage.SOURCE_CLIPBOARD_IMAGE)
        saved_image, _used_temp = modules.storage.save_image_to_managed_file(pasted_image.image, 1)
        filepath = modules.storage.current_image_path(saved_image)
        if filepath is None:
            msg = "saved generated image has no filepath"
            raise RuntimeError(msg)
        if not filepath.exists():
            msg = f"saved image path was not created: {filepath}"
            raise RuntimeError(msg)
        if image.get(modules.storage.PROP_MANAGED_PATH) != str(filepath):
            msg = "saved image path was not stamped on the image"
            raise RuntimeError(msg)
    finally:
        if filepath is not None:
            filepath.unlink(missing_ok=True)
        bpy.data.images.remove(image)


def check_generated_filenames_follow_preferences(modules: SimpleNamespace) -> None:
    original_values = modules.preferences.values

    for offset_hours in (-8, 0, 9):
        fixed_time = datetime(
            2026, 6, 3, 14, 35, 22, tzinfo=timezone(timedelta(hours=offset_hours))
        )
        filename = modules.preferences.render_generated_image_name(
            "{date}-{time}-{number}", number=7, now=fixed_time, blend_filepath=""
        )
        if filename != "20260603-143522-007.png":
            msg = f"generated name did not preserve local date/time tokens: {filename}"
            raise RuntimeError(msg)

    fixed_time = datetime(2026, 6, 3, 14, 35, 22, tzinfo=timezone(timedelta(hours=5)))

    filename = modules.preferences.render_generated_image_name(
        "{blend}-{date}-{time}-{number}",
        number=7,
        now=fixed_time,
        blend_filepath="/Users/example/concept-board.blend",
    )
    if filename != "concept-board-20260603-143522-007.png":
        msg = f"generated name did not render the main tokens: {filename}"
        raise RuntimeError(msg)

    filename = modules.preferences.render_generated_image_name(
        "{year}-{month}-{day}-{hour}-{minute}-{second}", number=7, now=fixed_time, blend_filepath=""
    )
    if filename != "2026-06-03-14-35-22.png":
        msg = f"generated name did not render date/time parts: {filename}"
        raise RuntimeError(msg)

    filename = modules.preferences.render_generated_image_name(
        "plate-{number:4}", number=7, now=fixed_time, blend_filepath=""
    )
    if filename != "plate-0007.png":
        msg = f"generated name did not render padded numbers: {filename}"
        raise RuntimeError(msg)

    def values_with_png_extension() -> object:
        return modules.preferences.PastyPreferences(generated_image_name="shot-{number}.png")

    def values_with_unsafe_chars() -> object:
        return modules.preferences.PastyPreferences(generated_image_name="shot/{number}:bad")

    try:
        modules.preferences.values = values_with_png_extension
        filename = modules.storage.generated_image_filename(7, ".png")
        if filename != "shot-007.png":
            msg = f"generated name duplicated or changed the extension: {filename}"
            raise RuntimeError(msg)

        modules.preferences.values = values_with_unsafe_chars
        filename = modules.storage.generated_image_filename(7, ".png")
        if filename != "shot-007-bad.png":
            msg = f"generated name was not made file-safe: {filename}"
            raise RuntimeError(msg)
    finally:
        modules.preferences.values = original_values


def check_unique_paths_do_not_overwrite(modules: SimpleNamespace) -> None:
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir)
        first_path = directory / "shot.png"
        second_path = directory / "shot-002.png"
        first_path.touch()
        path = modules.storage.unique_path(directory, "shot.png")
        if path != second_path:
            msg = f"expected collision path {second_path}, got {path}"
            raise RuntimeError(msg)

        second_path.touch()
        path = modules.storage.unique_path(directory, "shot.png")
        expected_path = directory / "shot-003.png"
        if path != expected_path:
            msg = f"expected second collision path {expected_path}, got {path}"
            raise RuntimeError(msg)


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
            pasted_images = [
                modules.clipboard.PastedImage(
                    first_image, modules.storage.SOURCE_COPIED_FILE, first_filepath
                ),
                modules.clipboard.PastedImage(
                    second_image, modules.storage.SOURCE_COPIED_FILE, second_filepath
                ),
            ]
            result = modules.sequencer.add_sequence_image_strips(
                strips, pasted_images, frame_start=1000
            )
            added_strips = result.strips
            if [modules.sequencer.sequence_strip_start(strip) for strip in added_strips] != [
                1000,
                1000 + modules.sequencer.sequence_strip_duration(),
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


def check_blender_relative_clipboard_paths_can_be_loaded(modules: SimpleNamespace) -> None:
    with TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)
        blend_path = project_dir / "pasty-relative-path.blend"
        image_dir = project_dir / "textures"
        image_dir.mkdir()
        filepath = image_dir / "project-relative.png"
        save_test_image(filepath, "pasty-project-relative-source", [0.25, 1.0, 0.25, 1.0])
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

        paths = modules.clipboard.image_file_paths_from_clipboard_text(
            "//textures/project-relative.png"
        )
        if paths != [filepath]:
            msg = f"unexpected project-relative clipboard paths: {paths}"
            raise RuntimeError(msg)


def check_platform_clipboard_file_paths_can_be_loaded(modules: SimpleNamespace) -> None:
    with TemporaryDirectory() as temp_dir:
        first_filepath = Path(temp_dir) / "pasty platform copied file.png"
        second_filepath = Path(temp_dir) / "pasty platform second file.PNG"
        not_image = Path(temp_dir) / "pasty platform notes.txt"
        save_test_image(first_filepath, "pasty-platform-source", [1.0, 0.5, 0.0, 1.0])
        save_test_image(second_filepath, "pasty-platform-second-source", [0.5, 0.0, 1.0, 1.0])
        not_image.write_text("not an image", encoding="utf-8")

        gnome_files_text = (
            f"copy\r\n# comment\r\n{first_filepath.as_uri()}\r\n"
            f"{not_image.as_uri()}\r\n{second_filepath.as_uri()}\r\n"
        )
        if modules.clipboard.image_file_paths_from_clipboard_text(gnome_files_text) != [
            first_filepath,
            second_filepath,
        ]:
            msg = "platform-style copied-file text was not parsed as image paths"
            raise RuntimeError(msg)

        original_platform_file_paths = modules.clipboard.platform_clipboard_file_paths
        original_clipboard_paste = modules.clipboard.image_clipboard_paste_result
        fake_context = SimpleNamespace(
            area=SimpleNamespace(type="VIEW_3D", ui_type="VIEW_3D"),
            window_manager=SimpleNamespace(clipboard=""),
        )

        try:
            modules.clipboard.platform_clipboard_file_paths = lambda: [
                first_filepath,
                not_image,
                second_filepath,
                first_filepath,
            ]
            modules.clipboard.image_clipboard_paste_result = clipboard_paste_poll_failed
            images = modules.clipboard.paste_images_from_clipboard(fake_context)
            try:
                if [image.source_path for image in images] != [first_filepath, second_filepath]:
                    msg = f"unexpected platform clipboard images: {images}"
                    raise RuntimeError(msg)
                if any(
                    image.image.get("pasty.source_kind") != modules.storage.SOURCE_COPIED_FILE
                    for image in images
                ):
                    msg = "platform copied files were not stamped as copied files"
                    raise RuntimeError(msg)
            finally:
                for image in images:
                    bpy.data.images.remove(image.image)
        finally:
            modules.clipboard.platform_clipboard_file_paths = original_platform_file_paths
            modules.clipboard.image_clipboard_paste_result = original_clipboard_paste


def check_clipboard_poll_failure_falls_back_to_paths(modules: SimpleNamespace) -> None:
    with TemporaryDirectory() as temp_dir:
        filepath = Path(temp_dir) / "pasty fallback path.png"
        save_test_image(filepath, "pasty-fallback-path-source-test", [0.0, 1.0, 1.0, 1.0])

        def no_platform_paths() -> list[Path]:
            return []

        original_platform_file_paths = modules.clipboard.platform_clipboard_file_paths
        original_clipboard_paste = modules.clipboard.image_clipboard_paste_result
        fake_context = SimpleNamespace(
            area=SimpleNamespace(type="VIEW_3D", ui_type="VIEW_3D"),
            window_manager=SimpleNamespace(clipboard=str(filepath)),
        )

        try:
            # Simulate Blender's image clipboard poll failure without needing a real GUI clipboard.
            modules.clipboard.platform_clipboard_file_paths = no_platform_paths
            modules.clipboard.image_clipboard_paste_result = clipboard_paste_poll_failed
            images = modules.clipboard.paste_images_from_clipboard(fake_context)
            try:
                if len(images) != 1:
                    msg = f"expected one fallback image, got {len(images)}"
                    raise RuntimeError(msg)
                if images[0].image.get("pasty.source_path") != str(filepath):
                    msg = "fallback image was not loaded from the clipboard path"
                    raise RuntimeError(msg)
            finally:
                for image in images:
                    bpy.data.images.remove(image.image)
        finally:
            modules.clipboard.platform_clipboard_file_paths = original_platform_file_paths
            modules.clipboard.image_clipboard_paste_result = original_clipboard_paste


def clipboard_paste_poll_failed() -> None:
    return None


def check_linux_clipboard_image_fallback_can_be_loaded(modules: SimpleNamespace) -> None:
    fixture = Path(__file__).resolve().parent / "fixtures" / "images" / "red.png"
    original_platform = modules.clipboard.sys.platform
    original_png_bytes = modules.clipboard.linux_clipboard_png_bytes
    try:
        modules.clipboard.sys.platform = "linux"
        modules.clipboard.linux_clipboard_png_bytes = fixture.read_bytes
        pasted_image = modules.clipboard.paste_linux_image_data_from_clipboard()
        if pasted_image is None:
            msg = "Linux clipboard image fallback did not load an image"
            raise RuntimeError(msg)
        try:
            if pasted_image.source_kind != modules.storage.SOURCE_CLIPBOARD_IMAGE:
                msg = f"unexpected Linux fallback source: {pasted_image.source_kind}"
                raise RuntimeError(msg)
            if pasted_image.image.packed_file is None:
                msg = "Linux fallback image was not packed before deleting its temp file"
                raise RuntimeError(msg)
            if pasted_image.image.filepath or pasted_image.image.filepath_raw:
                msg = "Linux fallback image kept a temporary filepath"
                raise RuntimeError(msg)
        finally:
            bpy.data.images.remove(pasted_image.image)
    finally:
        modules.clipboard.sys.platform = original_platform
        modules.clipboard.linux_clipboard_png_bytes = original_png_bytes


def check_linux_clipboard_tool_hint_is_shown_when_needed(modules: SimpleNamespace) -> None:
    original_platform = modules.clipboard.sys.platform
    original_reader_available = modules.clipboard.linux_png_reader_available
    original_writer_available = modules.clipboard.linux_png_writer_available
    try:
        modules.clipboard.sys.platform = "linux"
        modules.clipboard.linux_png_reader_available = lambda: False
        modules.clipboard.linux_png_writer_available = lambda: False
        if "install wl-clipboard" not in modules.clipboard.paste_failure_message():
            msg = "Linux paste failure did not explain the optional clipboard tools"
            raise RuntimeError(msg)
        if "install wl-clipboard" not in modules.clipboard.copy_failure_message():
            msg = "Linux copy failure did not explain the optional clipboard tools"
            raise RuntimeError(msg)
    finally:
        modules.clipboard.sys.platform = original_platform
        modules.clipboard.linux_png_reader_available = original_reader_available
        modules.clipboard.linux_png_writer_available = original_writer_available


def check_linux_clipboard_tools_follow_session(modules: SimpleNamespace) -> None:
    original_environ = dict(modules.clipboard.os.environ)
    original_executable_path = modules.clipboard.executable_path
    original_wl_png = modules.clipboard.linux_clipboard_png_bytes_with_wl_paste
    original_xclip_png = modules.clipboard.linux_clipboard_png_bytes_with_xclip

    def fake_executable_path(name: str) -> str | None:
        return f"/usr/bin/{name}" if name == "xclip" else None

    try:
        modules.clipboard.executable_path = fake_executable_path
        modules.clipboard.linux_clipboard_png_bytes_with_wl_paste = lambda: b""
        modules.clipboard.linux_clipboard_png_bytes_with_xclip = lambda: b"x11-png"

        modules.clipboard.os.environ.clear()
        modules.clipboard.os.environ.update({"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":99"})
        if modules.clipboard.linux_png_reader_available():
            msg = "Wayland reader availability fell through to xclip"
            raise RuntimeError(msg)
        if modules.clipboard.linux_clipboard_png_bytes():
            msg = "Wayland PNG reader fell through to xclip"
            raise RuntimeError(msg)

        modules.clipboard.os.environ.clear()
        modules.clipboard.os.environ.update({"DISPLAY": ":99"})
        if not modules.clipboard.linux_png_reader_available():
            msg = "X11 reader availability did not use xclip"
            raise RuntimeError(msg)
        if modules.clipboard.linux_clipboard_png_bytes() != b"x11-png":
            msg = "X11 PNG reader did not use xclip"
            raise RuntimeError(msg)
    finally:
        modules.clipboard.os.environ.clear()
        modules.clipboard.os.environ.update(original_environ)
        modules.clipboard.executable_path = original_executable_path
        modules.clipboard.linux_clipboard_png_bytes_with_wl_paste = original_wl_png
        modules.clipboard.linux_clipboard_png_bytes_with_xclip = original_xclip_png


def check_linux_clipboard_copy_fallback_writes_png(modules: SimpleNamespace) -> None:
    image = bpy.data.images.new("pasty-linux-copy-fallback", 2, 2)
    original_platform = modules.clipboard.sys.platform
    original_copy_png = modules.clipboard.copy_png_bytes_to_linux_clipboard
    captured = []

    def capture_png(png: bytes) -> bool:
        captured.append(png)
        return True

    try:
        image.pixels.foreach_set([1.0, 0.0, 0.0, 1.0] * 4)
        modules.clipboard.sys.platform = "linux"
        modules.clipboard.copy_png_bytes_to_linux_clipboard = capture_png
        if not modules.clipboard.copy_image_to_clipboard(SimpleNamespace(area=None), image):
            msg = "Linux copy fallback did not report success"
            raise RuntimeError(msg)
        if len(captured) != 1 or not captured[0].startswith(b"\x89PNG"):
            msg = "Linux copy fallback did not write PNG bytes"
            raise RuntimeError(msg)
    finally:
        modules.clipboard.sys.platform = original_platform
        modules.clipboard.copy_png_bytes_to_linux_clipboard = original_copy_png
        bpy.data.images.remove(image)


def check_clipboard_images_can_be_packed(modules: SimpleNamespace) -> None:
    image = bpy.data.images.new("pasty-pack-test", 2, 2)
    try:
        image.pixels.foreach_set([1.0, 0.0, 0.0, 1.0] * 4)
        modules.storage.pack_clipboard_image(image, 7)
        if image.packed_file is None:
            msg = "clipboard image was not packed"
            raise RuntimeError(msg)
        if image.get(modules.storage.PROP_STORAGE_KIND) != modules.storage.STORAGE_PACKED:
            msg = "packed clipboard image was not stamped as packed"
            raise RuntimeError(msg)
        if not image.name.startswith("pasted-") or not image.name.endswith("-007.png"):
            msg = f"packed clipboard image did not use the generated name: {image.name}"
            raise RuntimeError(msg)
    finally:
        bpy.data.images.remove(image)


def check_gather_updates_images_and_sequence_strips(modules: SimpleNamespace) -> None:
    scene = bpy.context.scene
    if scene is None:
        msg = "no active scene"
        raise RuntimeError(msg)

    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        blend_path = temp_path / "pasty-gather.blend"
        source_path = temp_path / "source-image.png"
        save_test_image(source_path, "pasty-gather-source", [0.5, 0.25, 1.0, 1.0])
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

        image = modules.clipboard.load_image_file(source_path)
        strips = None
        strip = None
        try:
            if image is None:
                msg = "could not load gather source image"
                raise RuntimeError(msg)

            sequence_editor = scene.sequence_editor or scene.sequence_editor_create()
            strips = modules.sequencer.sequence_collection(sequence_editor)
            strip = strips.new_image(
                name="pasty-gather-strip", filepath=str(source_path), channel=1, frame_start=2000
            )

            gathered = modules.storage.gather_pasted_images()
            if gathered != 1:
                msg = f"expected one gathered image, got {gathered}"
                raise RuntimeError(msg)
            if not source_path.exists():
                msg = "gather moved a user-owned source file instead of copying it"
                raise RuntimeError(msg)

            gathered_path = modules.storage.current_image_path(image)
            expected_dir = blend_path.parent / modules.preferences.DEFAULT_PASTED_IMAGES_FOLDER
            if gathered_path is None or gathered_path.parent != expected_dir:
                msg = f"unexpected gathered image path: {gathered_path}"
                raise RuntimeError(msg)
            if not gathered_path.exists():
                msg = f"gathered image file does not exist: {gathered_path}"
                raise RuntimeError(msg)

            strip_path = Path(bpy.path.abspath(strip.directory)) / strip.elements[0].filename
            if strip_path != gathered_path:
                msg = f"gather did not update the Sequencer strip path: {strip_path}"
                raise RuntimeError(msg)
        finally:
            if strips is not None and strip is not None:
                strips.remove(strip)
            if image is not None:
                bpy.data.images.remove(image)


def check_managed_copy_stays_in_current_folder(modules: SimpleNamespace) -> None:
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        first_project = temp_path / "first" / "first.blend"
        second_project = temp_path / "second" / "second.blend"
        first_project.parent.mkdir()
        second_project.parent.mkdir()
        source_path = temp_path / "source-image.png"
        save_test_image(source_path, "pasty-managed-source", [1.0, 0.0, 0.0, 1.0])
        bpy.ops.wm.save_as_mainfile(filepath=str(first_project))

        source_image = modules.clipboard.load_image_file(source_path)
        copied_images = []
        try:
            if source_image is None:
                msg = "could not load copied image for managed-copy test"
                raise RuntimeError(msg)

            pasted_image = modules.clipboard.PastedImage(
                source_image, modules.storage.SOURCE_COPIED_FILE, source_path
            )
            first_copy, _used_temp = modules.storage.copy_source_image_to_managed_file(pasted_image)
            copied_images.append(first_copy)
            first_path = modules.storage.current_image_path(first_copy)
            if first_path is None or first_path.parent != first_project.parent / "pasted-images":
                msg = f"unexpected first managed copy path: {first_path}"
                raise RuntimeError(msg)

            bpy.ops.wm.save_as_mainfile(filepath=str(second_project))
            second_copy, _used_temp = modules.storage.copy_source_image_to_managed_file(
                pasted_image
            )
            copied_images.append(second_copy)
            second_path = modules.storage.current_image_path(second_copy)
            if second_path is None or second_path.parent != second_project.parent / "pasted-images":
                msg = f"unexpected second managed copy path: {second_path}"
                raise RuntimeError(msg)
            if first_path == second_path:
                msg = "managed copy reused a file outside the current project folder"
                raise RuntimeError(msg)
        finally:
            removed_images = set()
            for image in copied_images:
                image_name = image.name
                if image_name in removed_images or image_name not in bpy.data.images:
                    continue
                bpy.data.images.remove(image)
                removed_images.add(image_name)
            if source_image is not None:
                bpy.data.images.remove(source_image)
