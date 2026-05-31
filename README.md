# Pasty

Pasty is a Blender add-on for pasting images from the system clipboard.

It adds paste actions for:

- 3D View: paste as a reference image
- 3D View: paste as a mesh plane
- Sequencer: paste as an image strip
- Shader Editor: paste as an image texture node

## Development

Developer setup lives in [docs/development.md](docs/development.md).

Technical design notes live in [docs/technical-design.md](docs/technical-design.md).

## Saved images

Blender stores clipboard images as generated image data. Sequencer strips need a real image file, so Pasty saves those pasted images to `//pasty` next to the `.blend` file. If the file has not been saved yet, Pasty uses the system temp folder.

## Blender and Python

The extension manifest lives in `blender_manifest.toml`. The add-on code lives in `__init__.py`, because Blender extension packages use that file as the add-on entry point.

The oldest supported Blender version is `4.2.0`. Blender `4.2.x` uses Python `3.11`, so this repo pins Python `3.11` too.
