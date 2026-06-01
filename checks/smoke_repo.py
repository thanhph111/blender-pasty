import sys
from pathlib import Path

# This file is run as `python checks/smoke_repo.py`, so Python starts from
# checks/. Add the repo root before importing the shared smoke checks.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks.blender import load_repo_addon, run_smoke_checks


def main() -> None:
    module = load_repo_addon()
    run_smoke_checks(module, register_addon=True)


if __name__ == "__main__":
    main()
