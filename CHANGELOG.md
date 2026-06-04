# Changelog

All notable changes to Pasty will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Pasty follows Blender add-on semantic versioning in spirit: `MAJOR.MINOR.PATCH`.

## [Unreleased]

### Added

- Read native copied image file lists from Windows, macOS, and common Linux clipboard tools before falling back to Blender image paste.

## [0.1.0] - 2026-06-01

First preview release.

### Added

- Paste clipboard images as 3D View reference images.
- Paste clipboard images as textured mesh planes.
- Paste clipboard images as Sequencer image strips.
- Paste clipboard images as Shader Editor image texture nodes.
- Copy images from 3D View objects and Shader Editor image texture nodes.
- Load copied image file paths and `file://` URLs when Blender does not find raw image data.
- Paste several copied image paths at once.

### Compatibility

- Blender 4.2.0 and newer.
- macOS, Windows, and Linux.

### Notes

- Linux clipboard behavior can differ between Wayland and X11.
