# This file can be run as a script, so Python starts from checks/addon. Add the
# repo root before importing the shared add-on behavior checks.
# ruff: noqa: E402, S607

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from checks.addon.behavior import load_repo_addon, run_blender_checks


def main() -> None:
    subprocess.run(["mise", "run", "validate"], cwd=ROOT, check=True)
    module = load_repo_addon()
    run_blender_checks(module, register_addon=True)


if __name__ == "__main__":
    main()
