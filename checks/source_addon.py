import sys
from pathlib import Path

# This file can be run as a script, so Python starts from checks/. Add the repo
# root before importing the shared add-on behavior checks.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks.addon_behavior import load_repo_addon, run_blender_checks


def main() -> None:
    module = load_repo_addon()
    run_blender_checks(module, register_addon=True)


if __name__ == "__main__":
    main()
