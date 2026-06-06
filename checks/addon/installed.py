import importlib
import os
import sys
from pathlib import Path

import addon_utils

# Blender runs this as a file, so Python starts from checks/addon. Add the repo
# root before importing the shared add-on behavior checks.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from checks.addon.behavior import run_blender_checks


def main() -> None:
    module_name = os.environ.get("PASTY_EXTENSION_MODULE", "bl_ext.pasty_package_test.pasty")

    is_default_enabled, is_loaded = addon_utils.check(module_name)
    if not is_loaded:
        # install-file --enable normally handles this. Keep the explicit enable so this
        # installed add-on check also works after a plain install-file call.
        addon_utils.enable(module_name, default_set=False, persistent=False)

    module = importlib.import_module(module_name)
    run_blender_checks(module, register_addon=False)

    if not is_default_enabled:
        addon_utils.disable(module_name, default_set=False)


if __name__ == "__main__":
    main()
