# Changelog

All notable changes to Pasty will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Pasty follows Blender add-on semantic versioning in spirit: `MAJOR.MINOR.PATCH`.

## [Unreleased]

### Added

- Add Pasty preferences for pasted image storage, generated PNG names, and Sequencer still image length.
- Add `File > External Data > Gather Pasted Images` to copy Pasty-marked external images into the project folder.
- Add support for image files copied directly from Finder, Explorer, and common Linux file managers.
- Add live clipboard check commands for copied files, image paste, and image copy on macOS, Windows, Linux X11, and Linux Wayland.
- Add optional Linux `image/png` clipboard fallback through `wl-clipboard` or `xclip` when Blender cannot read the image clipboard itself.

### Changed

- Clipboard images pasted into the 3D View and Shader Editor are now packed into the `.blend` by default.
- Sequencer clipboard images are now saved to `//pasted-images` by default.
- Copied image files now keep their original file paths by default unless `Copy to Folder` is enabled.

## [0.1.0] - 2026-06-01

First preview release.

### Added

- Paste clipboard images as 3D View reference images.
- Paste clipboard images as textured mesh planes.
- Paste clipboard images as Sequencer image strips.
- Paste clipboard images as Shader Editor image texture nodes.
- Copy images from 3D View objects and Shader Editor image texture nodes.
- Load copied image file paths and `file://` URLs when Blender does not find clipboard image data.
- Paste several copied image paths at once.

### Compatibility

- Blender 4.2.0 and newer.
- macOS, Windows, and Linux.

### Notes

- Linux clipboard behavior can differ between Wayland and X11.
