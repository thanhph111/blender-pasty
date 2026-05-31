# Pasty

Pasty is a Blender add-on for pasting images from the system clipboard.

It first uses Blender's native image clipboard support. If the clipboard contains image file paths or `file://` URLs instead, Pasty can load those files too. Several image paths paste as several images.

It adds paste actions for:

- 3D View: paste as a reference image
- 3D View: paste as a mesh plane
- Sequencer: paste as an image strip
- Shader Editor: paste as an image texture node

It also adds copy actions for image objects, material image textures, and Shader Editor image texture nodes.

## Development

Developer setup lives in [docs/development.md](docs/development.md).

Technical design notes live in [docs/technical-design.md](docs/technical-design.md).

## Saved images

Blender stores raw clipboard images as generated image data. Sequencer strips need a real image file, so Pasty saves generated images to `//pasty` next to the `.blend` file. If the file has not been saved yet, Pasty uses the system temp folder.

## Blender and Python

The extension manifest lives in `blender_manifest.toml`. The add-on code lives in `__init__.py`, because Blender extension packages use that file as the add-on entry point.

The oldest supported Blender version is `4.2.0`. Blender `4.2.x` uses Python `3.11`, so this repo pins Python `3.11` too.
