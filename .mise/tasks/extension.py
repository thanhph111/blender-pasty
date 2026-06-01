#!/usr/bin/env -S uv run -s --no-sync

# [MISE] description="Run Blender extension commands"

import os
import shutil
import subprocess
import sys


def main() -> None:
    # Honor BLENDER_BIN for users who keep Blender outside PATH.
    blender_path = os.environ.get("BLENDER_BIN") or shutil.which("blender")

    if blender_path:
        run_blender_extension(blender_path)
        return

    run_bpy_extension()


def run_blender_extension(blender_path: str) -> None:
    try:
        result = subprocess.run([blender_path, "--command", "extension", *sys.argv[1:]], check=True)
    except subprocess.CalledProcessError as error:
        print(f"Blender command failed: {error}", file=sys.stderr)
        sys.exit(error.returncode)
    except OSError as error:
        print(f"Could not run Blender: {error}", file=sys.stderr)
        sys.exit(1)

    sys.exit(result.returncode)


def run_bpy_extension() -> None:
    try:
        # GitHub checks can validate/build through the bpy wheel when full
        # Blender is not present.
        import bpy  # noqa: F401
        from bl_pkg.bl_extension_cli import cli_extension_handler  # ty: ignore[unresolved-import]
    except ImportError as error:
        print(f"Blender not found and bpy/bl_pkg modules not available: {error}", file=sys.stderr)
        sys.exit(1)

    cli_extension_handler(sys.argv[1:])


if __name__ == "__main__":
    main()
