import importlib
from typing import Any

# Blender installs this package under bl_ext.<repo>.pasty, while smoke tests load
# it as pasty_smoke. Build child imports from the runtime package name so both
# paths use the same entry point.
package_name = __package__ or __name__

blender_types = importlib.import_module(f"{package_name}.addon.blender_types")
preferences = importlib.import_module(f"{package_name}.addon.preferences")
storage = importlib.import_module(f"{package_name}.addon.storage")
clipboard = importlib.import_module(f"{package_name}.addon.clipboard")
image_lookup = importlib.import_module(f"{package_name}.addon.image_lookup")
sequencer = importlib.import_module(f"{package_name}.addon.areas.sequencer")
shader_editor = importlib.import_module(f"{package_name}.addon.areas.shader_editor")
view_3d = importlib.import_module(f"{package_name}.addon.areas.view_3d")
registration: Any = importlib.import_module(f"{package_name}.addon.registration")

# Blender loads this root file as the extension package. The real code lives in
# addon/ so the repo has room to grow without turning this entry point into a
# catch-all file again.
#
# Reload Scripts runs this package again in the same Python process. Reload leaf
# modules first, then registration, so class and menu references point at the
# newest code after an edit.
if "register" in locals():
    importlib.reload(blender_types)
    importlib.reload(preferences)
    importlib.reload(storage)
    importlib.reload(clipboard)
    importlib.reload(image_lookup)
    importlib.reload(sequencer)
    importlib.reload(shader_editor)
    importlib.reload(view_3d)
    importlib.reload(registration)

classes = registration.classes
register = registration.register
unregister = registration.unregister
