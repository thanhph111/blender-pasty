# Manual testing

Use this checklist when changing clipboard behavior. Headless tests can prove the Blender API pieces, but they cannot prove the real system clipboard on every desktop.

## Setup

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

## Clipboard sources

Check these sources on each platform you care about:

- Screenshot copied to the clipboard
- Image copied from a browser
- Image copied from an image editor
- One image file path copied as text
- Several image file paths copied as text
- One `file://` URL copied as text
- Several `file://` URLs copied as text

For Linux, test both Wayland and X11 if possible. Blender's native image clipboard support can behave differently between them.

## Paste targets

For each clipboard source, test these targets:

- 3D View: `Paste as Reference`
- 3D View: `Paste as Plane`
- Sequencer: `Paste from Clipboard`
- Shader Editor: `Paste from Clipboard`

Expected behavior:

- Raw clipboard image data pastes as one image.
- Several image file paths paste as several target items.
- Sequencer strips use the first free channel for their frame range.
- Shader Editor paste replaces a selected Image Texture node.
- Shader Editor paste links the first pasted image to a selected Principled BSDF.

## Copy targets

Check these copy paths:

- 3D View image empty
- 3D View mesh object with an image texture material
- Shader Editor selected Image Texture node

After copying from Blender, paste into an image editor or another Blender area to confirm the image data reached the system clipboard.

## Notes to record

When a platform fails, record:

- Blender version
- Operating system and desktop session, such as macOS, Windows, Linux Wayland, or Linux X11
- Clipboard source app
- Pasty target area
- Whether Blender's own Image Editor clipboard paste works
- The exact warning or error shown by Pasty
