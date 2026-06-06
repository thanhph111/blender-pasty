# Development

This repo uses `mise` as the command runner. `mise` pins the tools used by the repo, so local commands and GitHub checks use the same versions.

For the product vision and preference design, see [product-design.md](product-design.md).

For code boundaries and ImagePaste comparison, see [technical-design.md](technical-design.md).

For real clipboard checks, release checks, and packaged install testing, see [testing.md](testing.md).

For release publishing, see [release.md](release.md).

## Setup

Run this once:

```bash
mise trust
mise run setup
```

Common checks:

```bash
mise run lint
mise run test
mise run test package
mise run test linux x11
mise run build
```

`mise run test` validates the extension manifest and runs the source add-on behavior checks.

`mise run test package` builds the extension zip, installs that zip into a clean temporary Blender extension repository, enables it, and runs the checks against the installed extension.

`mise run test linux x11` runs the Linux X11 clipboard checks in Docker. Use `mise run test linux wayland` for the Wayland lab.

`mise run build` writes the extension zip to `dist/`.

## Commits

Commit messages use Conventional Commits:

```text
type(scope): description
```

Examples:

```text
chore(tooling): refresh development workflow
fix(addon): save pasted sequencer images
ci(blender): test clipboard paste in official builds
```

## Source layout

The root `__init__.py` is Blender's entry point. The rest of the add-on code lives in `addon/`:

```text
__init__.py
addon/
  clipboard.py
  image_lookup.py
  preferences.py
  registration.py
  storage.py
  areas/
    view_3d.py
    shader_editor.py
    sequencer.py
```

This keeps Blender's expected root package shape and avoids a build staging step.

## Live Blender testing

For day-to-day development, use a symlinked local extension folder. A symlink is a folder shortcut, so Blender reads this repo directly instead of a copied file.

Create the symlink:

```bash
mise run dev link
```

Print the exact paths:

```bash
mise run dev paths
```

Add the dev folder to Blender:

```bash
mise run dev repo-add
```

If `mise run dev repo-add` cannot find Blender, open Blender and add the dev folder printed by `mise run dev paths`:

```text
Edit > Preferences > Get Extensions > Repositories
```

In Blender, enable `Pasty` once. After editing source files, use:

```text
Blender > System > Reload Scripts
```

Most placement edits will be in `addon/areas/`. Clipboard source edits live in `addon/clipboard.py`. File handling edits live in `addon/storage.py`.

To test the packaged extension instead of the live symlink:

```bash
mise run dev install
```

To install into another Blender extension repository:

```bash
mise run dev install --repo user_default
```

### Cross-platform notes

The live setup uses symlinks. Symlinks are better than copying on save here because Blender sees the latest files after each save. Save the file, then reload scripts in Blender.

Default dev folders:

```text
macOS/Linux: ~/Blender/dev-extensions
Windows:     ~/Documents/Blender/dev-extensions
```

On Windows, symlinks need Developer Mode or an administrator shell. If your team uses a different folder, set `PASTY_DEV_EXTENSIONS_DIR`.

## Debugging

Run Blender with `debugpy` listening:

```bash
mise run dev debug --wait
```

Then use the `Attach to Blender` launch config in `blender-pasty.code-workspace`.

The first debug run installs `debugpy` into `.cache/blender-debugpy` for Blender's own Python. This keeps Blender away from the repo `.venv`, which may use a different Python version.

Set `BLENDER_BIN` if Blender is not on `PATH`. Dev commands that launch Blender use it:

```bash
BLENDER_BIN=/path/to/blender mise run dev debug --wait
```

## Task map

```text
mise run deps             install project dependencies
mise run setup            install dependencies and Git hooks
mise run lint             run formatters and linters
mise run test            validate the manifest and check the source add-on
mise run test source     same as mise run test
mise run test package    build, install, and check the packaged zip
mise run test clipboard  run live clipboard checks on the current desktop
mise run test linux x11  run Linux X11 clipboard checks in Docker
mise run test linux wayland
                         run Linux Wayland clipboard checks in Docker
mise run test linux all  run both Docker Linux clipboard checks
mise run build            build dist/pasty-*.zip
mise run release-notes    print release notes from CHANGELOG.md
mise run blender install  install a Blender build for automated checks
mise run blender run      run the Blender binary used by automated checks
mise run dev paths        print dev paths
mise run dev link         symlink the repo into the dev extension folder
mise run dev repo-add     add the dev extension folder to Blender
mise run dev install      build and install the packaged extension
mise run dev debug        launch Blender with debugpy listening
```

## GitHub checks

`.github/workflows/checks.yml` runs the PR commit-message check, then calls `.github/workflows/_verify.yml`.

The shared checks workflow runs lint, source add-on checks, Linux live clipboard checks, headless Blender checks, then installed add-on checks. The full release-candidate run checks Linux, Windows, and Apple Silicon macOS in headless Blender, plus the Linux live clipboard sessions listed in [testing.md](testing.md).
