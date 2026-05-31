# Development

This repo uses `mise` as the command runner. `mise` pins the tools used by the repo, so local commands and CI use the same versions.

For the add-on design and ImagePaste comparison, see [technical-design.md](technical-design.md).

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
mise run build
```

`mise run test` runs the repo-side pytest tests, validates the extension manifest, and runs a headless Blender API smoke test.

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

In Blender, enable `Pasty` once. After editing `__init__.py`, use:

```text
Blender > System > Reload Scripts
```

To test the packaged extension instead of the live symlink:

```bash
mise run dev install
```

To install into another Blender extension repository:

```bash
mise run dev install --repo user_default
```

### Cross-platform notes

The live setup uses a symlink. A symlink is better than copying on save here because Blender reads this repo directly. Save the file, then reload scripts in Blender.

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

Set `BLENDER_BIN` if Blender is not on `PATH`:

```bash
BLENDER_BIN=/path/to/blender mise run dev debug --wait
```

## Task map

```text
mise run deps          install project dependencies
mise run setup         install dependencies and Git hooks
mise run lint          run formatters and linters
mise run test          run pytest, validate the manifest, and smoke-test the add-on
mise run build         build dist/pasty-*.zip
mise run dev paths     print dev paths
mise run dev link      symlink the repo into the dev extension folder
mise run dev repo-add  add the dev extension folder to Blender
mise run dev install   build and install the packaged extension
mise run dev debug     launch Blender with debugpy listening
```

## CI

`.github/workflows/ci.yml` runs the fast checks: lint, test, then build.

`.github/workflows/blender.yml` runs the heavier Blender matrix. It downloads official Blender builds and runs the headless smoke test across Linux, Windows, macOS arm64, and macOS Intel.
