# This check runs Docker Compose for the local Linux clipboard lab.
# ruff: noqa: E402, S603, S607

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from checks.clipboard.scenarios import SCENARIOS

SESSIONS = ("x11", "wayland")


def main() -> None:
    parser = argparse.ArgumentParser(prog="linux run", description="Run Docker Linux tests")
    parser.add_argument("session", nargs="?", choices=("all", *SESSIONS), default="all")
    parser.add_argument("scenario", nargs="?", choices=("all", *SCENARIOS), default="all")
    args = parser.parse_args()

    test_linux(args.session, args.scenario)


def test_linux(session: str, scenario: str) -> None:
    sessions = SESSIONS if session == "all" else (session,)
    for current_session in sessions:
        run_linux_docker(current_session, scenario)


def run_linux_docker(session: str, scenario: str) -> None:
    service = f"linux-{session}"
    env = os.environ.copy()
    env["PASTY_CLIPBOARD_SCENARIO"] = scenario
    run(
        [*docker_compose_command(), "--profile", service, "run", "--rm", "--build", service],
        env=env,
    )


def docker_compose_command() -> list[str]:
    if shutil.which("docker") is not None:
        result = subprocess.run(
            ["docker", "compose", "version"],
            check=False,
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return ["docker", "compose"]
    if shutil.which("docker-compose") is not None:
        return ["docker-compose"]

    msg = "Docker Compose not found. Install Docker Desktop or Docker Compose."
    raise RuntimeError(msg)


def run(command: list[str], env: dict[str, str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True, env=env)


if __name__ == "__main__":
    main()
