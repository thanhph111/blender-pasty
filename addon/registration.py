import bpy

from .areas import sequencer, shader_editor, view_3d

area_modules = (view_3d, sequencer, shader_editor)

classes = tuple(cls for area_module in area_modules for cls in area_module.classes)
menu_hooks = tuple(hook for area_module in area_modules for hook in area_module.menu_hooks)
keymap_specs = tuple(spec for area_module in area_modules for spec in area_module.keymap_specs)

addon_keymaps: list[tuple[bpy.types.KeyMap, bpy.types.KeyMapItem]] = []


def register() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)
    for menu, draw in menu_hooks:
        menu.append(draw)
    register_keymaps()


def unregister() -> None:
    unregister_keymaps()
    for menu, draw in reversed(menu_hooks):
        menu.remove(draw)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


def register_keymaps() -> None:
    if addon_keymaps:
        return

    if bpy.context.window_manager is None:
        # Headless checks have no window manager, but register() still needs to succeed.
        return

    kc = bpy.context.window_manager.keyconfigs.addon
    if not kc:
        # Some startup states have no add-on keyconfig yet.
        return

    for keymap_name, space_type, operator_id, modifiers in keymap_specs:
        km = kc.keymaps.new(name=keymap_name, space_type=space_type)
        kmi = km.keymap_items.new(operator_id, type="V", value="PRESS", **modifiers)
        addon_keymaps.append((km, kmi))


def unregister_keymaps() -> None:
    # Track only keymaps we created so reload/unregister does not touch user shortcuts.
    for km, kmi in reversed(addon_keymaps):
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
