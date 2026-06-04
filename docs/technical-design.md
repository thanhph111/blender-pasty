# Technical design

Pasty is a Blender extension for pasting images from the system clipboard into common Blender work areas.

| Area          | Result             |
| ------------- | ------------------ |
| 3D View       | Reference image    |
| 3D View       | Mesh plane         |
| Sequencer     | Image strip        |
| Shader Editor | Image texture node |

For the product principles behind these choices, see [product-design.md](product-design.md).

## Core idea

Pasty treats a paste as two steps:

1. Find the best image source from the clipboard.
2. Prepare that image for the target Blender area.

The source order is intentional:

```text
copied image files
clipboard image
```

Copied files are checked first because they keep names, formats, paths, and multi-file selections. Pasty can find copied files through native file-list formats, plain paths, or `file://` URLs.

If no copied image files are found, Pasty uses Blender's own image clipboard operator:

```python
bpy.ops.image.clipboard_paste()
```

Pasty does not try to read operating-system image pixels itself. It lets Blender do that work.

Copied file support has two layers. Pasty reads native copied-file formats where they preserve more information, and also reads Blender's text clipboard for image file paths and `file://` URLs. Several paths become several pasted images.

The platform layer stays file-list-only:

- Windows reads `CF_HDROP`, the standard copied-file list from Explorer.
- macOS reads pasteboard file URLs from `/usr/bin/osascript` and AppKit.
- Linux reads `text/uri-list` and `x-special/gnome-copied-files` through `wl-paste` or `xclip` when those tools are installed.

If those readers fail or are not available, Pasty falls back quietly.

This matters because clipboard image handling is different across macOS, Windows, Linux X11, Linux Wayland, screenshots, browsers, Photoshop, ShareX, and copied image files. Rebuilding all of that inside the add-on creates a lot of fragile platform code.

## Paste flow

Blender's image clipboard paste operator belongs to the Image Editor. If Pasty needs Blender to read a copied screenshot or copied browser image while the user is in the 3D View, Sequencer, or Shader Editor, Pasty briefly switches the current area to the Image Editor, runs Blender's paste command, then switches the area back.

```mermaid
flowchart TD
    A["User runs a Pasty paste command"] --> B["Pasty remembers the current editor"]
    B --> C["Pasty checks copied image files, paths, and file URLs"]
    C --> D{"Did Pasty load image files?"}
    D -->|"Yes"| G["Pasty prepares images for the target area"]
    D -->|"No"| E["Pasty switches that area to the Image Editor"]
    E --> F["Blender reads the clipboard image"]
    F --> I["Pasty restores the original editor"]
    I --> H{"Did Blender create an image?"}
    H -->|"Yes"| G
    H -->|"No"| J["Pasty reports that no compatible image was found"]
```

The shared paste path lives in `temporary_image_editor()`, `paste_images_from_clipboard()`, and the image file helpers in `addon/clipboard.py`.

`addon/storage.py` owns what happens after a source is found:

- use the original file
- pack into the `.blend`
- save to the pasted images folder
- save to Blender's temporary folder
- gather pasted images beside the `.blend`

The editor-specific behavior lives with the editor it changes:

- `addon/areas/view_3d.py`
- `addon/areas/shader_editor.py`
- `addon/areas/sequencer.py`

`addon/preferences.py` owns the small preferences panel and the generated filename template renderer. Storage uses that renderer, so the preview in preferences and the actual saved file names mean the same thing.

`addon/registration.py` owns classes, menus, and shortcuts.

## Poll rules

Blender calls an operator's `poll()` method to decide whether a button, menu item, or shortcut should be enabled.

Pasty keeps `poll()` simple. It only checks the current editor and mode.

For example, a 3D View paste operator checks that Blender is in the 3D View and Object Mode. A Shader Editor paste operator checks that the current node editor has an active node tree.

Pasty does not check the clipboard inside `poll()`.

That is intentional. Checking the clipboard would require temporarily switching the current area to the Image Editor. Blender may call `poll()` often while drawing UI, so changing editors there can cause flicker or strange behavior.

Clipboard work only happens when the user actually runs a paste command.

## 3D view reference paste

When you paste as a reference, Pasty gets an image from copied files or from Blender's clipboard paste, prepares storage, adds an Image Empty in the 3D View, and assigns the pasted image to that Empty. The result is a normal Blender image reference object.

If several image files are copied, Pasty creates one reference object per image and offsets them slightly.

## 3D view mesh plane paste

When you paste as a mesh plane, Pasty first creates the same image reference object. It then asks Blender to convert that selected reference image into a textured mesh plane.

Pasty uses Blender's built-in operator:

```python
bpy.ops.image.convert_to_mesh_plane()
```

This is better than manually building the mesh, material, UVs, and texture node setup. Blender already owns that behavior.

If several image files are copied, Pasty creates one mesh plane per image and offsets them slightly.

## Shader editor paste

When you paste in the Shader Editor, Pasty uses the current node selection:

- If an Image Texture node is selected, Pasty replaces that node's image.
- If a Principled BSDF node is selected, Pasty links the image color to Base Color.
- Otherwise Pasty creates an Image Texture node at the cursor.

If several image files are copied, Pasty creates a vertical stack of image texture nodes. If an Image Texture node is selected, the first image replaces it and the remaining images become nearby nodes.

## Sequencer paste

The Sequencer is different.

Sequencer image strips need a real image file path.

So Sequencer paste has one extra storage step: every pasted image must resolve to a file path before Pasty creates the image strip.

If the image came from a file path, Pasty uses the original path by default.

If the image came from Blender's clipboard paste, Pasty saves the pasted image as a PNG.

If several image files are copied, Pasty creates strips in a row starting at the current frame.

Generated clipboard file names use the preference template:

```text
pasted-{date}-{time}-{number}
```

The template is the file name stem. Pasty always adds the fixed `.png` suffix because generated clipboard files are saved as PNG.

The supported tokens are `{date}`, `{time}`, `{number}`, `{number:4}`, `{blend}`, `{year}`, `{month}`, `{day}`, `{hour}`, `{minute}`, and `{second}`. Date and time tokens use the user's local clock. `{number:4}` means a four-digit number such as `0001`. These cover the common naming patterns without turning the add-on into a file naming language.

If a generated file name already exists, Pasty appends a number such as `-002`. It never overwrites existing files.

If the `.blend` file is saved, Pasty writes to:

```text
//pasted-images
```

That means a `pasted-images` folder next to the `.blend` file.

If the `.blend` file has not been saved yet, Pasty writes to Blender's temporary folder and marks those files so `Gather Pasted Images` can move them later.

Because of this, the extension manifest declares both permissions:

```toml
[permissions]
clipboard = "Copy and paste images to/from the system clipboard"
files = "Load image files and save generated clipboard images"
```

## Comparison with ImagePaste

[ImagePaste](https://github.com/b-init/ImagePaste) is the older Blender add-on in this space. Its README says it supports pasting images into the Image Editor, Video Sequencer, Shader Editor, and 3D Viewport. It also says the add-on is expected to be deprecated as the functionality is integrated into Blender.

ImagePaste reads the operating system clipboard with platform-specific code, saves an image file, then loads that file into Blender.

It has separate clipboard code for each platform:

- macOS uses a native pasteboard module plus `osascript`
- Linux uses a bundled `xclip` binary
- Windows uses PowerShell and .NET clipboard APIs

That approach made sense before Blender had better built-in image clipboard support, but it creates many moving parts.

Pasty uses copied image files first, then asks Blender to read the clipboard image. It saves a file only when the target requires a file path or when the user chooses `Save to Folder`.

The goal is not to become a bigger ImagePaste. The goal is to be smaller, more native to modern Blender, and less platform-fragile.

## Why Pasty uses Blender clipboard support

These ImagePaste issues show where platform clipboard code and older Blender APIs can break. These examples were checked on May 31, 2026.

- macOS native pasteboard import failures: [#55](https://github.com/b-init/ImagePaste/issues/55), [#60](https://github.com/b-init/ImagePaste/issues/60), [#61](https://github.com/b-init/ImagePaste/issues/61)
- Linux `xclip` or process failures: [#35](https://github.com/b-init/ImagePaste/issues/35), [#51](https://github.com/b-init/ImagePaste/issues/51), [#62](https://github.com/b-init/ImagePaste/issues/62)
- Windows clipboard format gaps: [#23](https://github.com/b-init/ImagePaste/issues/23), [#38](https://github.com/b-init/ImagePaste/issues/38), [#39](https://github.com/b-init/ImagePaste/issues/39)
- Blender API churn around reference images and image planes: [#56](https://github.com/b-init/ImagePaste/issues/56), [#59](https://github.com/b-init/ImagePaste/issues/59), [#66](https://github.com/b-init/ImagePaste/issues/66)
- Blender 5 Sequencer API breakage: [#65](https://github.com/b-init/ImagePaste/issues/65)
- Save-handler/operator breakage in Blender 4.5: [#64](https://github.com/b-init/ImagePaste/issues/64)
- Unclear save folder behavior: [#26](https://github.com/b-init/ImagePaste/issues/26)

Pasty avoids most of this by not owning platform image extraction. Blender owns clipboard image reading. Pasty only adds a small copied-file reader so file-manager copies can keep their original paths, names, formats, and multi-file selection.

## What Pasty does not try to do

Pasty intentionally does not try to be a full ImagePaste clone.

It does not support:

- raw OS-specific image clipboard extraction
- moving user-owned files
- moving all images in a `.blend`
- save-time file moving
- SVG or text clipboard handling

Those features can be added later, but they should be added only when they fit the small native design.

## Current limits

Pasty depends on Blender's own image clipboard support.

That means behavior can differ by platform. Blender's image clipboard support is strongest on Windows, macOS, and Linux Wayland.

Multiple-image paste works for copied file lists, clipboard text that exposes several image paths, or several file URLs. It does not mean Blender's native image clipboard operator can read several clipboard images at once.

Linux X11 may be weaker depending on Blender and the desktop environment.

This is still better than shipping our own image clipboard stack, because Blender itself is the owner of clipboard image support.

## Design rules

- Use Blender's own operators when Blender already owns the behavior.
- Read native copied-file lists only to preserve file paths and multi-file paste.
- Do not read raw operating-system image data; Blender owns that.
- Do not switch editor areas inside `poll()`.
- Treat copied files and copied pixels as different sources.
- Never move a user-owned file.
- Let `storage.py` own pack, save, temporary-folder, and gather decisions.
- Keep the add-on small. A paste utility should not become a clipboard framework.

## Testing

Headless tests can check:

- the add-on imports
- operators are registered
- operators are unregistered
- generated images can be saved to disk
- image file paths and file URLs can be loaded
- multiple image file paths create multiple target items
- gathered images are copied beside the `.blend` without moving user files

Real clipboard behavior needs a local GUI smoke test, because headless Blender cannot fully prove system clipboard behavior. Hosted GitHub runners do not give us a stable system clipboard.

Manual GUI checks should cover copying an image to the clipboard, then pasting as a 3D reference, as a 3D plane, into the Sequencer, and into the Shader Editor.

## References

- [Blender image operators](https://docs.blender.org/api/4.2/bpy.ops.image.html)
- [Blender extension manifest permissions](https://docs.blender.org/manual/en/4.2/advanced/extensions/getting_started.html)
- [Microsoft Shell Clipboard Formats](https://learn.microsoft.com/en-us/windows/win32/shell/clipboard)
- [Apple NSPasteboard](https://developer.apple.com/documentation/AppKit/NSPasteboard)
- [wl-paste manual](https://man.archlinux.org/man/wl-paste.1.en)
- [ImagePaste repository](https://github.com/b-init/ImagePaste)
- [ImagePaste operators](https://github.com/b-init/ImagePaste/blob/main/imagepaste/operators.py)
- [ImagePaste macOS clipboard code](https://github.com/b-init/ImagePaste/blob/main/imagepaste/clipboard/darwin/darwin.py)
- [ImagePaste Linux clipboard code](https://github.com/b-init/ImagePaste/blob/main/imagepaste/clipboard/linux/linux.py)
- [ImagePaste Windows clipboard code](https://github.com/b-init/ImagePaste/blob/main/imagepaste/clipboard/windows/windows.py)
