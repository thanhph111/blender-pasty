# Testing

Use this guide when changing clipboard behavior or preparing a release.

Headless tests can check Blender's Python API, package install, and registration. They cannot prove that the real desktop clipboard works on every platform, so manual GUI checks still matter.

## Automated checks

Run these from the repo root:

```bash
mise run lint
mise run test
mise run test package
```

`mise run test` validates the extension manifest and runs a headless Blender API smoke test.

`mise run test package` builds `dist/pasty-*.zip`, installs that zip into a clean temporary Blender extension repository, enables it, and runs the smoke checks against the installed extension module.

## Day-to-day manual setup

Use the live symlink while developing:

```bash
mise run dev link
mise run dev repo-add
```

In Blender, enable `Pasty`. After code changes, use:

```text
Blender > System > Reload Scripts
```

To test the packaged extension instead:

```bash
mise run dev install
```

## Release targets

Before publishing, test on:

- Blender 4.2 LTS
- Blender 4.5 LTS
- The current stable Blender version

Also test on:

- macOS
- Windows
- Linux Wayland
- Linux X11

Linux needs both Wayland and X11 when possible because clipboard behavior can differ between desktop sessions.

## Test files

Use the tiny files in `checks/fixtures/images/` for copied-path testing:

- `red.png`
- `green.png`
- `blue.png`

They are intentionally small so they can stay in the repo and be copied around freely.

## Clipboard sources

Check these sources:

- Screenshot copied to the clipboard
- Image copied from a browser
- Image copied from an image editor
- One image file path copied as text
- Several image file paths copied as text
- One `file://` URL copied as text
- Several `file://` URLs copied as text

For path tests, use the fixture images. Copy both plain file paths and `file://` URLs.

## Paste targets

For each clipboard source, test these targets:

- 3D View: `Add > Image > Paste as Reference`
- 3D View: `Add > Image > Paste as Plane`
- Sequencer: right-click, `Paste from Clipboard`
- Shader Editor: right-click, `Paste from Clipboard`

Expected behavior:

- Raw clipboard image data pastes as one image.
- Several copied image paths paste as several target items.
- 3D View paste offsets several pasted images so they do not fully overlap.
- Sequencer strips use the first free channel for their frame range.
- Sequencer paste creates strips in a row from the current frame.
- Shader Editor paste replaces a selected Image Texture node.
- Shader Editor paste links the first pasted image to a selected Principled BSDF node.

## Copy targets

Check these copy paths:

- 3D View image reference object
- 3D View mesh object with an image texture material
- Shader Editor selected Image Texture node

After copying from Blender, paste into an image editor or another Blender area to confirm the image reached the system clipboard.

## Packaged install

Before a release, test the actual zip, not only the live repo:

```bash
mise run build
```

Then in Blender:

1. Open `Edit > Preferences > Get Extensions`.
2. Choose `Install from Disk`.
3. Select `dist/pasty-0.1.0.zip`.
4. Enable `Pasty`.
5. Run the paste and copy checks above.

## Notes to record

When a platform fails, record:

- Blender version
- Operating system and desktop session, such as macOS, Windows, Linux Wayland, or Linux X11
- Clipboard source app
- Pasty target area
- Whether Blender's own Image Editor clipboard paste works
- The warning or error shown by Pasty
