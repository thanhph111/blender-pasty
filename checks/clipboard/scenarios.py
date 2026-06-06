from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "checks" / "fixtures" / "images"

SCENARIOS = ("copied-files", "paste-image", "copy-image")
COPIED_FILE_FIXTURES = (FIXTURE_DIR / "red.png", FIXTURE_DIR / "green.png")
