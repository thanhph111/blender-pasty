import os
import subprocess
import sys


def main() -> None:
    blender_bin = os.environ.get("BLENDER_BIN")
    if not blender_bin:
        msg = "BLENDER_BIN is not set"
        raise RuntimeError(msg)

    subprocess.run([blender_bin, *sys.argv[1:]], check=True)


if __name__ == "__main__":
    main()
