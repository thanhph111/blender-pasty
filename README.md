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

Pasty is meant to supersede the older ImagePaste-style workflow for modern Blender.

ImagePaste solved a real problem by reading the operating system clipboard with platform-specific code. Pasty keeps the same spirit, but uses Blender's own image clipboard support first. That makes the add-on smaller and less fragile across macOS, Windows, Linux X11, Linux Wayland, screenshots, browsers, and image editors.

If Blender does not find raw image data, Pasty also checks Blender's text clipboard for image file paths and `file://` URLs. Several copied paths paste as several images.

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

Right-click in the Shader Editor and choose `Paste from Clipboard`.

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

Right-click in the Sequencer and choose `Paste from Clipboard`.

Pasty creates image strips starting at the current frame. If several image paths are copied, Pasty places the strips in a row.

Shortcut:

- `Ctrl Shift Alt V`: paste from clipboard

<!-- TODO: add screenshot of Sequencer context menu. -->
<!-- TODO: add GIF showing several copied image paths becoming several image strips. -->

## Saved images

Blender can keep a raw clipboard image as generated image data. Generated image data lives inside Blender and may not have a real file path.

Sequencer image strips need a real file path, so Pasty saves generated clipboard images before creating strips.

If the `.blend` file is saved, Pasty writes generated images to:

```text
//pasty
```

That means a `pasty` folder next to the `.blend` file.

If the `.blend` file has not been saved yet, Pasty writes generated images to the system temp folder and shows a warning.

## Notes

Clipboard support can vary by operating system and source app. If a screenshot or copied browser image does not paste, check whether Blender's own Image Editor paste works first.

Linux users should test the same workflow on their actual desktop session. Wayland and X11 can behave differently.

## Development

Developer setup lives in [docs/development.md](docs/development.md).

Technical design notes live in [docs/technical-design.md](docs/technical-design.md).

Testing notes live in [docs/testing.md](docs/testing.md).

Release notes live in [CHANGELOG.md](CHANGELOG.md).

## License

Pasty is licensed under GPL-3.0-or-later.
