from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import bpy

# This file is run by Blender, so Python starts from checks/clipboard. Add the
# repo root before importing the shared add-on behavior helpers.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from checks.addon.behavior import addon_modules, load_repo_addon
from checks.clipboard.scenarios import COPIED_FILE_FIXTURES, SCENARIOS

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import SimpleNamespace

RESULT_ENV = "PASTY_CLIPBOARD_RESULT"
RELEASE_ENV = "PASTY_CLIPBOARD_RELEASE"
INPUT_READY_ENV = "PASTY_CLIPBOARD_INPUT_READY"
INPUT_SENT_ENV = "PASTY_CLIPBOARD_INPUT_SENT"
RELEASE_TIMEOUT_SECONDS = 30
INPUT_TIMEOUT_SECONDS = 30


def main() -> None:
    parser = argparse.ArgumentParser(prog="clipboard blender")
    parser.add_argument("scenario", choices=(*SCENARIOS, "all"), default="all", nargs="?")
    args = parser.parse_args(blender_args())

    if bpy.app.background:
        run_from_timer(args.scenario)
        return

    # Clipboard operators need Blender's GUI to finish one event-loop tick.
    # Running them during startup can hang on an idle desktop.
    schedule_run(args.scenario)


def schedule_run(scenario: str) -> None:
    if not os.environ.get(INPUT_READY_ENV):
        bpy.app.timers.register(lambda: run_from_timer(scenario), first_interval=0.5)
        return

    # Wayland only accepts clipboard ownership from a recent GUI input event.
    # The outer test process sends that event, then writes INPUT_SENT_ENV. If
    # Blender did not receive a usable serial, the real clipboard copy below
    # will fail during OS verification.
    schedule_after_input_run(scenario)


def schedule_after_input_run(scenario: str) -> None:
    Path(os.environ[INPUT_READY_ENV]).write_text("ready", encoding="utf-8")
    input_sent_path = os.environ.get(INPUT_SENT_ENV)
    if not input_sent_path:
        error = RuntimeError("Clipboard input sent marker is not configured.")
        write_result(ok=False, error=error)
        bpy.ops.wm.quit_blender()
        return

    deadline = time.monotonic() + INPUT_TIMEOUT_SECONDS

    def wait_for_input_sent() -> float | None:
        if Path(input_sent_path).is_file():
            run_from_timer(scenario)
            return None
        if time.monotonic() > deadline:
            error = RuntimeError("Timed out waiting for the Wayland clipboard input signal.")
            write_result(ok=False, error=error)
            bpy.ops.wm.quit_blender()
            return None
        return 0.1

    bpy.app.timers.register(wait_for_input_sent, first_interval=0.5)


def run_from_timer(scenario: str) -> None:
    try:
        run_checks(scenario)
    except Exception as error:  # noqa: BLE001
        traceback.print_exc()
        write_result(ok=False, error=error)
        bpy.ops.wm.quit_blender()
    else:
        write_result(ok=True)
        wait_for_release_or_quit()


def write_result(*, ok: bool, error: Exception | None = None) -> None:
    result_path = os.environ.get(RESULT_ENV)
    if not result_path:
        return

    payload: dict[str, object] = {"ok": ok}
    if error is not None:
        payload["error"] = str(error)
        payload["traceback"] = traceback.format_exc()
    Path(result_path).write_text(json.dumps(payload), encoding="utf-8")


def wait_for_release_or_quit() -> None:
    release_path = os.environ.get(RELEASE_ENV)
    if not release_path:
        bpy.ops.wm.quit_blender()
        return

    # Wayland clipboard data is owned by the app that offers it. Keep Blender's
    # event loop alive so an external wl-paste check can request the copied PNG.
    deadline = time.monotonic() + RELEASE_TIMEOUT_SECONDS

    def check_release() -> float | None:
        if Path(release_path).is_file():
            bpy.ops.wm.quit_blender()
            return None
        if time.monotonic() > deadline:
            error = RuntimeError("Timed out waiting for clipboard verification release.")
            write_result(ok=False, error=error)
            bpy.ops.wm.quit_blender()
            return None
        return 0.1

    bpy.app.timers.register(check_release, first_interval=0.1)


def run_checks(scenario: str) -> None:
    module = load_repo_addon()
    modules = addon_modules(module)

    for current_scenario in SCENARIOS if scenario == "all" else (scenario,):
        if current_scenario == "copied-files":
            check_copied_files(modules)
        elif current_scenario == "paste-image":
            check_paste_image(modules)
        elif current_scenario == "copy-image":
            check_copy_image(modules)


def blender_args() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


def check_copied_files(modules: SimpleNamespace) -> None:
    expected_paths = [path.resolve(strict=False) for path in COPIED_FILE_FIXTURES]
    missing_paths = [path for path in expected_paths if not path.is_file()]
    if missing_paths:
        msg = f"missing clipboard check fixtures: {missing_paths}"
        raise RuntimeError(msg)

    actual_paths = [
        path.resolve(strict=False) for path in modules.clipboard.platform_clipboard_file_paths()
    ]
    if actual_paths != expected_paths:
        msg = f"unexpected platform clipboard file paths: {actual_paths}"
        raise RuntimeError(msg)

    images = []
    with clipboard_context() as context:
        images = modules.clipboard.paste_images_from_clipboard(context)
    try:
        actual_image_paths = [
            image.source_path.resolve(strict=False)
            for image in images
            if image.source_path is not None
        ]
        if actual_image_paths != expected_paths:
            msg = f"unexpected pasted image paths: {actual_image_paths}"
            raise RuntimeError(msg)
        if any(
            image.image.get("pasty.source_kind") != modules.storage.SOURCE_COPIED_FILE
            for image in images
        ):
            msg = "copied files were not stamped as copied files"
            raise RuntimeError(msg)
    finally:
        remove_images([image.image for image in images])


def check_paste_image(modules: SimpleNamespace) -> None:
    images = []
    with clipboard_context() as context:
        images = modules.clipboard.paste_images_from_clipboard(context)
    try:
        if len(images) != 1:
            msg = f"expected one pasted clipboard image, got {len(images)}"
            raise RuntimeError(msg)
        image = images[0]
        if image.source_kind != modules.storage.SOURCE_CLIPBOARD_IMAGE:
            msg = f"expected clipboard image source, got {image.source_kind}"
            raise RuntimeError(msg)
        if image.image.size[0] < 1 or image.image.size[1] < 1:
            msg = "pasted clipboard image has no pixel size"
            raise RuntimeError(msg)
    finally:
        remove_images([image.image for image in images])


def check_copy_image(modules: SimpleNamespace) -> None:
    image = bpy.data.images.new("pasty-copy-clipboard-check", 2, 2)
    try:
        image.pixels.foreach_set([1.0, 0.0, 0.0, 1.0] * 4)
        with clipboard_context() as context:
            if not modules.clipboard.copy_image_to_clipboard(context, image):
                msg = "Pasty copy did not put an image on the clipboard"
                raise RuntimeError(msg)
    finally:
        remove_images([image])


@contextmanager
def clipboard_context() -> Iterator[bpy.types.Context]:
    if bpy.app.background:
        yield bpy.context
        return

    window = bpy.context.window
    screen = window.screen if window is not None else None
    if screen is None:
        yield bpy.context
        return

    area = next((candidate for candidate in screen.areas if candidate.type != "TOPBAR"), None)
    if area is None:
        yield bpy.context
        return

    region = next((candidate for candidate in area.regions if candidate.type == "WINDOW"), None)
    if region is None:
        yield bpy.context
        return

    with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
        yield bpy.context


def remove_images(images: list[bpy.types.Image]) -> None:
    for image in images:
        if image.name in bpy.data.images:
            bpy.data.images.remove(image)


if __name__ == "__main__":
    main()
