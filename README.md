# Pasty

Pasty is a Blender extension for pasting images from the system clipboard into the places where artists usually need them.

It can paste images into:

- 3D View: reference image
- 3D View: textured mesh plane
- Sequencer: image strip
- Shader Editor: image texture node

It can also copy images back to the clipboard from image reference objects, textured mesh objects, and Shader Editor image texture nodes.

<!-- TODO: add hero GIF showing copy from browser, paste as plane, paste into Shader Editor, paste into Sequencer. -->

## Why Pasty

Pasty builds on the older ImagePaste idea for modern Blender.

ImagePaste solved a real problem by reading the operating system clipboard with platform-specific code. Pasty keeps the same spirit, but keeps the platform layer narrow: it reads copied file lists when the operating system exposes them, then uses Blender's own image clipboard support for screenshots, browsers, and image editors.

Pasty checks copied image files first, including Finder, Explorer, common Linux file-manager formats, plain paths, and `file://` URLs. Several copied files paste as several images. If no image files are found, Pasty asks Blender for a screenshot or image copied from a browser or image editor.

## Install

Download the latest `pasty-*.zip` from the GitHub Releases page.

In Blender:

1. Open `Edit > Preferences > Get Extensions`.
2. Use the menu in the top right and choose `Install from Disk`.
3. Select the downloaded `pasty-*.zip`.
4. Enable `Pasty`.

Pasty supports Blender `4.2.0` and newer.

## Use

### 3D view

Use `Add > Image > Paste as Reference` to paste the clipboard image as an image reference object.

Use `Add > Image > Paste as Plane` to paste the clipboard image as a textured mesh plane.

Right-click an image reference object, or a mesh object with an image texture material, and choose `Copy Image` to copy that image back to the system clipboard.

Shortcuts:

- `Ctrl Shift Alt V`: paste as reference
- `Ctrl Shift V`: paste as plane

<!-- TODO: add screenshot of the 3D View Add > Image menu. -->
<!-- TODO: add GIF showing several copied image paths becoming several offset reference images. -->

### Shader editor

Right-click in the Shader Editor and choose `Paste Image Texture`.

Pasty follows the current node selection:

- If an Image Texture node is selected, Pasty replaces that node's image.
- If a Principled BSDF node is selected, Pasty creates an Image Texture node and links it to Base Color.
- Otherwise, Pasty creates an Image Texture node at the cursor.

Right-click a selected Image Texture node and choose `Copy Image` to copy its image to the system clipboard.

Shortcut:

- `Ctrl Shift V`: paste from clipboard

<!-- TODO: add screenshot of Shader Editor context menu. -->
<!-- TODO: add GIF showing paste over selected Image Texture node. -->

### Sequencer

Right-click in the Sequencer and choose `Paste Image Strip`.

Pasty creates image strips starting at the current frame. If several image paths are copied, Pasty places the strips in a row.

Shortcut:

- `Ctrl Shift Alt V`: paste from clipboard

<!-- TODO: add screenshot of Sequencer context menu. -->
<!-- TODO: add GIF showing several copied image paths becoming several image strips. -->

## Saved images and project folders

Pasty follows Blender's normal file model:

- Copied image paths use the original files by default.
- Clipboard images are packed into the `.blend` by default. Save the `.blend` before sharing it.
- Sequencer image strips need real files, so clipboard images pasted into the Sequencer are saved as PNG files.

These defaults keep copied library files untouched and keep screenshots or browser images with the `.blend`.

If the `.blend` file is saved, Sequencer clipboard images are saved to:

```text
//pasted-images
```

That means a `pasted-images` folder next to the `.blend` file.

If the `.blend` file has not been saved yet, Sequencer clipboard images are saved to Blender's temporary folder and Pasty shows a warning.

To gather pasted images beside the `.blend`, use:

```text
File > External Data > Gather Pasted Images
```

This copies user-owned pasted files and moves only temporary files created by Pasty.

If you pasted before saving the `.blend`, save the file first, then run `Gather Pasted Images`.

<!-- TODO: add screenshot of Pasty preferences showing Storage, Naming, and Sequencer settings. -->

## File name templates

Pasty uses `Generated File Name` for clipboard images that need a PNG file. The field is the name pattern only. Pasty shows and adds the fixed `.png` suffix.

Default:

```text
pasted-{date}-{time}-{number}
```

Examples:

| Template                        | Fixed suffix | Example result                   |
| ------------------------------- | ------------ | -------------------------------- |
| `pasted-{date}-{time}-{number}` | `.png`       | `pasted-20260603-143522-001.png` |
| `{blend}-{number:4}`            | `.png`       | `project-0001.png`               |
| `shot-{year}-{month}-{day}`     | `.png`       | `shot-2026-06-03.png`            |

Tokens:

| Token        | Meaning                                      | Example    |
| ------------ | -------------------------------------------- | ---------- |
| `{date}`     | Local date as `YYYYMMDD`                     | `20260603` |
| `{time}`     | Local time as `HHMMSS`                       | `143522`   |
| `{number}`   | Three-digit paste number                     | `001`      |
| `{number:4}` | Paste number with the digit width you choose | `0001`     |
| `{blend}`    | Current `.blend` file name without `.blend`  | `project`  |
| `{year}`     | Four-digit year                              | `2026`     |
| `{month}`    | Two-digit month                              | `06`       |
| `{day}`      | Two-digit day                                | `03`       |
| `{hour}`     | Two-digit hour, 24-hour clock                | `14`       |
| `{minute}`   | Two-digit minute                             | `35`       |
| `{second}`   | Two-digit second                             | `22`       |

Pasty always writes generated clipboard files as PNG. Leave `.png` out of the template field; the suffix is shown beside the field and added for you.

Pasty does not overwrite existing files. If the name already exists, Pasty adds a number:

```text
pasted-20260603-143522-001.png
pasted-20260603-143522-001-002.png
```

## Notes

Clipboard support can vary by operating system and source app. If a screenshot or copied browser image does not paste, check whether Blender's own Image Editor paste works first.

Linux users should test the same workflow on their actual desktop session. Wayland and X11 can behave differently.

## Development

Developer setup lives in [docs/development.md](docs/development.md).

Technical design notes live in [docs/technical-design.md](docs/technical-design.md).

Product design notes live in [docs/product-design.md](docs/product-design.md).

Testing notes live in [docs/testing.md](docs/testing.md).

Release notes live in [CHANGELOG.md](CHANGELOG.md).

## License

Pasty is licensed under GPL-3.0-or-later.
