# Testing

Use this guide when changing clipboard behavior or preparing a release.

Pasty uses custom checks, not pytest. Blender is the real test runner for this add-on, so the checks stay close to Blender operators, Blender data-blocks, and the live desktop clipboard.

The release rule is simple: automated checks are the release gate. Manual testing is still useful, but only for exploring source apps and desktops that CI cannot name one by one.

## Test areas

The repo has four test areas:

| Area              | Main command              | What it proves                                                                             |
| ----------------- | ------------------------- | ------------------------------------------------------------------------------------------ |
| Source behavior   | `mise run test`           | The source checkout imports, registers, unregisters, and handles normal add-on behavior.   |
| Package behavior  | `mise run test package`   | The built zip installs, enables, validates, and works as a real Blender extension.         |
| Current desktop   | `mise run test clipboard` | The current operating-system clipboard works with the current Blender binary.              |
| Linux desktop lab | `mise run test linux x11` | Docker can run a known Linux desktop session and check the real clipboard path end to end. |

Use `mise run test linux wayland` for the Wayland lab and `mise run test linux all` for both Linux labs.

`check` means one small rule or script.

The folder is named `checks/` because these files are custom Blender-first checks. They are not a pytest test suite.

## Commands

Run these from the repo root:

```bash
mise run lint
mise run test
mise run test package
mise run test clipboard all
mise run test linux x11
mise run test linux wayland
```

`mise run test` defaults to source checks. `mise run test source` is the same command written out.

`mise run test package` builds `dist/pasty-*.zip`, installs that zip into a clean temporary Blender extension repository, enables it, and runs the checks against the installed extension module.

`mise run test clipboard all` runs every live clipboard scenario supported by the current desktop session.

The normal local gate is:

```bash
mise run lint
mise run test
mise run test package
```

The local release gate is:

```bash
mise run lint
mise run test
mise run test package
mise run test clipboard all
mise run test linux all
```

You can run one clipboard scenario:

```bash
mise run test clipboard copied-files
mise run test clipboard paste-image
mise run test clipboard copy-image
```

The same scenario argument works for the Docker Linux checks:

```bash
mise run test linux x11 paste-image
mise run test linux wayland copy-image
```

The clipboard checks replace the current operating-system clipboard while they run. Do not run them in parallel.

If Blender is not on `PATH`, set `BLENDER_BIN`:

```bash
BLENDER_BIN=/Applications/Blender.app/Contents/MacOS/Blender mise run test clipboard all
```

For the Docker Linux checks, choose the Blender series with `PASTY_BLENDER_VERSION`:

```bash
PASTY_BLENDER_VERSION=<series> mise run test linux x11
PASTY_BLENDER_VERSION=<series> mise run test linux wayland
```

## Check files

`checks/addon/behavior.py` owns shared add-on behavior checks.

Use it for parser rules, registration cleanup, storage behavior, installed add-on checks, and small mocked-clipboard tests that do not need a real desktop clipboard.

`checks/addon/source.py` validates the manifest and runs those checks against the source checkout.

`checks/addon/package.py` builds the zip, installs it into a clean extension repository, validates it, and starts the installed add-on check.

`checks/addon/installed.py` runs those checks against the installed zip.

`checks/clipboard/run.py` owns live clipboard scenario order, Blender process handling, timeouts, result files, and Wayland input signaling.

`checks/clipboard/os.py` owns operating-system clipboard setup and verification.

This helper does not import the add-on. It only seeds or reads the real OS clipboard. Normal development should still go through `mise run test clipboard ...`; the helper is an internal part of that task.

`checks/clipboard/blender.py` owns Blender-side live clipboard verification.

It runs inside Blender and supports:

- `copied-files`
- `paste-image`
- `copy-image`
- `all`

`checks/clipboard/scenarios.py` owns shared live clipboard scenario names and fixture paths.

`checks/linux/x11.sh` owns the X11 display setup.

`checks/linux/wayland.sh` owns the Wayland display setup.

`checks/linux/run.py` owns Docker Compose routing for the local Linux lab.

`checks/linux/docker.sh` owns the Docker entry point. It installs the requested Blender version, sets `BLENDER_BIN`, and runs the X11 or Wayland script.

`.github/workflows/scripts/plan_targets.py` owns the GitHub target lists for fast and full runs.

## Clipboard scenarios

`copied-files` seeds two fixture files into the real OS clipboard, verifies the OS clipboard exposes both paths, starts Blender, and checks that Pasty pastes both images as copied files.

`paste-image` seeds PNG bytes into the real OS clipboard, starts Blender, and checks that Pasty pastes one clipboard image. On Linux X11, this proves Pasty's narrow Linux fallback because Blender native image paste does not support X11 image clipboards.

`copy-image` starts Blender, creates a tiny image, runs Pasty's copy command, asks the OS helper to verify image data while Blender is still open, then lets Blender quit. That matters on Wayland because clipboard image data is served by the app that owns the clipboard offer. Automated Wayland checks send a real GUI input event before the copy, matching the moment when an artist presses a key in the UI.

On Linux Wayland, the automated `copy-image` check needs `wtype` or `ydotool` so it can send the GUI input event Wayland requires before Blender owns the copied image. The Docker image includes both, and CI installs both on the Ubuntu runner.

## Headless coverage

Headless checks cover:

- plain image paths
- `file://` URLs
- `text/uri-list`
- GNOME copied-file text
- comments and `copy`/`cut` markers
- duplicate paths
- non-image files
- Blender `//` paths
- copied-file paste source stamps
- clipboard image pack and save behavior
- gather behavior
- class and keymap cleanup after unregister
- Linux image/png paste and copy fallback using mocked readers and writers

## Fixtures

Use the tiny files in `checks/fixtures/images/`:

- `red.png`
- `green.png`
- `blue.png`

They are intentionally small so they can stay in the repo and be copied around freely.

## CI profiles

The fast profile runs on pull requests. It keeps feedback short:

- lint
- source add-on checks
- installed add-on checks
- fast headless Blender matrix
- one Linux X11 live clipboard check

The full profile runs on pushes to `main`. It adds the full hosted live clipboard matrix.

`.github/workflows/scripts/plan_targets.py` owns the exact hosted Blender versions, runners, and any runner-specific exclusions. Keep the list there so docs do not drift from CI.

Linux X11 uses the GitHub runner directly with `xvfb` and `xclip`.

Linux Wayland uses the GitHub runner directly with a headless Sway session, `wl-clipboard`, `wtype`, `ydotool`, and `ydotoold`. `wtype` sends a Wayland keyboard event for the copy check. `ydotool` and `ydotoold` are kept as a backup when the runner exposes `/dev/uinput`.

Blender 4.5 is still checked in Linux X11 live clipboard jobs and in the full headless matrix. It is not a hosted Linux Wayland live clipboard gate because Blender exits in headless Sway during image paste before Pasty can write a result. The product behavior is the same across these jobs.

Hosted macOS and Windows runners still run headless Blender checks in the full profile, but they are not treated as live clipboard release gates. Pasty depends on Blender's native image clipboard support on those platforms, and hosted runners do not give us the same controlled desktop session as a logged-in artist machine.

Run macOS and Windows live clipboard checks locally with `mise run test clipboard all`. With real desktop self-hosted runners, those jobs can become release gates without changing product code.

## Docker Linux lab

Docker is a local Linux lab. It gives macOS and Windows developers a repeatable Linux X11 or Wayland desktop without turning GitHub Actions into Docker inside Docker.

Run the same scenarios locally:

```bash
mise run test linux x11
mise run test linux wayland
mise run test linux all copied-files
```

The Docker image owns Linux display packages and Blender installation. GitHub Actions installs the same display packages on the runner and calls `checks/linux/x11.sh` or `checks/linux/wayland.sh` directly.

The workflow graph uses these gates:

| Gate                       | What it proves                                                                                             |
| -------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `lint`                     | Text, formatting, Python style, Markdown, workflow syntax, and types are clean.                            |
| `source-addon`             | The source checkout imports, registers, unregisters, and passes the shared add-on behavior checks.         |
| `headless-blender-targets` | The workflow chooses the Blender versions and platforms for headless checks.                               |
| `headless-blender`         | Official Blender builds can run the source checkout in background mode.                                    |
| `live-clipboard-targets`   | The workflow chooses the desktop clipboard sessions for live checks.                                       |
| `live-clipboard`           | Linux desktop clipboards can paste copied files, paste image data, and receive copied image data.          |
| `installed-addon`          | The built zip installs, enables, validates, and passes the same behavior checks as an installed extension. |

## Writing checks

Put behavior that can run without a live desktop clipboard in `checks/addon/behavior.py`.

Put OS clipboard seeding or OS clipboard reading in `checks/clipboard/os.py`.

Put Blender-side live clipboard assertions in `checks/clipboard/blender.py`.

Keep each check direct. Prefer fixture images and plain assertions over a new test framework.

## Manual exploration

Manual checks are for learning, not for release blocking.

Good exploratory sources:

- screenshot copied to the clipboard
- image copied from a browser
- image copied from an image editor
- one image file copied from the file manager
- several image files copied from the file manager
- plain file paths copied as text
- `file://` URLs copied as text

Good exploratory targets:

- 3D View: `Add > Image > Paste as Reference`
- 3D View: `Add > Image > Paste as Plane`
- Sequencer: right-click, `Paste Image Strip`
- Shader Editor: right-click, `Paste Image Texture`

If a platform fails, record:

- Blender version
- operating system and desktop session, such as macOS, Windows, Linux Wayland, or Linux X11
- clipboard source app
- Pasty target area
- whether the source was copied files, text paths, file URLs, or image pixels
- whether Blender's own Image Editor clipboard paste works
- the warning or error shown by Pasty
