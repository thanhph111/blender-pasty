# Product design

This document records the long-term product shape for Pasty. It keeps file handling, preferences, and naming aligned with the goal: paste images into Blender without turning the add-on into a file manager.

## Product promise

Pasty lets artists paste images into the Blender area where they are already working.

The default experience should feel like this:

```text
Copy an image.
Paste in Blender.
Keep working.
```

File handling matters, but it should stay quiet until the artist needs to move, share, or clean up the project.

## Design principles

### Match artist intent

Copied files and copied pixels mean different things.

If the clipboard contains image files, Pasty should use those files first. Files keep their names, formats, source paths, and multi-file selection.

If the clipboard contains pixels from a screenshot, browser, or image editor, Pasty should treat that as a new pasted image.

Blender should read those pixels first. Pasty adds platform image readers only where Blender leaves a known gap. Today that means a Linux `image/png` reader through `wl-clipboard` or `xclip` after Blender fails.

Successful Linux fallback should stay quiet. If fallback is needed but the tool is missing, Pasty should show a short install hint. Standard desktop clipboard tools are found through `PATH`, so the preferences stay focused on storage and naming.

### Use Blender's own model

Blender already has clear ideas for image ownership:

- linked external files
- packed files inside the `.blend`
- relative paths such as `//textures/image.png`
- External Data commands for packing, unpacking, and missing files

Pasty should use those ideas instead of inventing its own asset system.

### Keep settings separate

Each preference should answer one clear question.

Avoid overlapping controls where two settings can fight each other. Expose a setting only when it gives artists a clear workflow choice.

### Prefer defaults that work for most artists

Most users should not need to open Pasty preferences.

The defaults should cover common work:

- paste a browser image as a reference
- paste a screenshot into a material
- paste copied image files
- paste still images into the Sequencer
- send a `.blend` with pasted 3D View and Shader Editor clipboard images included

Advanced users can still gather files or change naming, but those controls should not interrupt normal paste.

### Respect the file system

Pasty never moves a file the artist copied from disk.

Moving user files can break texture libraries, shared folders, other projects, or the user's own Downloads/Desktop organization. User-owned files may be copied when the user chooses to gather or copy into the pasted images folder.

Pasty may move only temporary files it created itself. The safe order is: copy first, update Blender paths, then delete the temporary file after success.

## User-facing storage words

Use these words in the interface and docs:

- `Use Originals`
- `Copy to Folder`
- `Pack into .blend`
- `Save to Folder`
- `Gather Pasted Images`

The folder row is named `Pasted Images Folder`, so the short button labels can stay short without becoming vague.

Avoid words like:

- project-local
- migration
- clipboard pixels
- data-block
- sync
- manage assets

Those words are either too technical or imply that Pasty is bigger than a paste tool.

## Storage behavior

### Copied image files

Default: `Use Originals`

Blender points to the copied files where they already live.

Optional: `Copy to Folder`

Pasty copies the files beside the `.blend` when they are pasted. The original files stay where they are.

### Clipboard images

Default: `Pack into .blend`

For 3D View and Shader Editor, Pasty packs pasted clipboard images into the `.blend`. Packing means Blender stores the image inside the blend file after the file is saved.

Optional: `Save to Folder`

Pasty saves pasted clipboard images beside the `.blend`.

### Sequencer images

The Sequencer needs real image file paths. It cannot use a packed image as the strip source.

For copied image files, Pasty uses the original path or a copied project file, depending on the copied-file preference.

For clipboard images, Pasty saves PNG files.

If the `.blend` is unsaved, Pasty saves those files to Blender's temporary folder and reports:

```text
Unsaved .blend: pasted images were saved to Blender's temporary folder. Save the file, then run Gather Pasted Images.
```

### Gather pasted images

`Gather Pasted Images` is the explicit project cleanup command.

It belongs in `File > External Data`, near Blender's own file tools.

The command:

- copies user-owned pasted files into the pasted images folder
- moves Pasty-owned temporary files into the pasted images folder
- updates image paths and Sequencer image strip paths
- never touches images that were not marked as pasted by Pasty

## Preferences

The preferences panel stays small.

The panel uses Blender's existing add-on frame. Inside that frame, use plain section labels and aligned rows.

Storage:

| Setting                | Control                 | Choices or default                   |
| ---------------------- | ----------------------- | ------------------------------------ |
| `Copied Image Files`   | side-by-side choice row | `Use Originals`, `Copy to Folder`    |
| `Clipboard Images`     | side-by-side choice row | `Pack into .blend`, `Save to Folder` |
| `Pasted Images Folder` | text field              | `pasted-images`                      |

Naming:

| Setting               | Control    | Default                         |
| --------------------- | ---------- | ------------------------------- |
| `Generated File Name` | text field | `pasted-{date}-{time}-{number}` |

Keep token help outside the compact preferences panel. The panel shows the field and a short preview; user docs carry the full token reference.

Sequencer:

| Setting                       | Control      | Default     |
| ----------------------------- | ------------ | ----------- |
| `Still Image Length (Frames)` | number field | `50 frames` |

## Default choices

The defaults are chosen for the common paste-and-keep-working path.

`Copied Image Files`: `Use Originals`

Copied files are already real files. Their names, folders, formats, and library locations often matter. Using the original files avoids unnecessary copies and keeps texture-library workflows intact.

`Clipboard Images`: `Pack into .blend`

Screenshots, browser images, and image-editor pixels often have no meaningful source file. Packing keeps the pasted image with the `.blend` for 3D View and Shader Editor work, so users do not lose it when sharing or moving the file.

`Pasted Images Folder`: `pasted-images`

When Pasty must write files, the folder should be easy to recognize, easy to delete, and next to the `.blend`. The name says what owns the files without pretending they are a full texture library.

`Generated File Name`: `pasted-{date}-{time}-{number}` with fixed `.png`

Generated clipboard images need stable names that sort by paste time and do not collide easily. Date, time, and number cover the common case without asking users to understand templates first. The `.png` suffix is fixed because generated clipboard images are saved as PNG.

`Still Image Length (Frames)`: `50`

Fifty frames is a small, visible strip length for Blender's usual timeline defaults. It is long enough to see and move in the Sequencer, but short enough that several pasted stills can sit in a row without taking over the edit.

Out of scope:

- a source-order preference
- a copied-file naming preference
- a temporary-folder picker
- a move-all-images option
- a save-time move handler
- clipboard backend choices
- clipboard tool path settings
- debug message toggles
- a full asset-manager panel

## Naming rules

Generated names are for images Pasty creates from clipboard pixels.

The name template is a stable user-facing feature.

Supported tokens:

| Token        | Meaning                                            | Example    |
| ------------ | -------------------------------------------------- | ---------- |
| `{date}`     | Local date as `YYYYMMDD`                           | `20260603` |
| `{time}`     | Local time as `HHMMSS`                             | `143522`   |
| `{number}`   | Three-digit paste number                           | `001`      |
| `{number:4}` | Paste number with the digit width the user chooses | `0001`     |
| `{blend}`    | Current `.blend` file name without `.blend`        | `project`  |
| `{year}`     | Four-digit year                                    | `2026`     |
| `{month}`    | Two-digit month                                    | `06`       |
| `{day}`      | Two-digit day                                      | `03`       |
| `{hour}`     | Two-digit hour, 24-hour clock                      | `14`       |
| `{minute}`   | Two-digit minute                                   | `35`       |
| `{second}`   | Two-digit second                                   | `22`       |

Pasty always saves generated clipboard files as PNG. The settings UI shows `.png` as a fixed suffix beside the pattern field. Users should think of the field as the name stem, not the full file name.

Pasty chooses a unique file name, so it does not need an overwrite warning.

The visible panel shows the field and preview. The full token table belongs in user docs.

Copied files always keep their original names because the name often carries meaning, such as `wood_basecolor.png` or `logo_blue.png`.

If generated names collide, Pasty appends a number instead of overwriting:

```text
pasted-20260603-143522-001.png
pasted-20260603-143522-001-002.png
```

## Feature boundaries

Pasty keeps these owners:

```text
clipboard.py   finds copied files or clipboard pixels
storage.py     decides use original, pack, save, temporary folder, and gather
preferences.py exposes the small preferences panel
areas/         places images in Blender editors
```

Clipboard code finds sources; it does not decide where files live.

Sequencer code creates strips; it does not own project folder rules.

Preferences expose user choices, not internal implementation details.

## ImagePaste comparison

ImagePaste solved an important problem, but it also handles many file-system tasks: custom folders, filename tokens, move modes, save handlers, and broad platform image clipboard readers.

Pasty keeps the parts that help the artist:

- side-by-side storage choices
- a filename pattern with a fixed `.png` suffix
- a clear token table in user docs

Pasty leaves out the heavier parts:

- bundled platform clipboard binaries
- broad platform image clipboard readers
- automatic file moving on save
- broad image migration tools
- settings that overlap Blender's own file tools

Pasty does read native copied-file lists. It also has a narrow Linux `image/png` fallback through optional desktop tools. Those small platform pieces preserve normal artist actions: copy several image files from a file manager, or copy a screenshot/browser image on Linux X11, then paste into Blender without extra setup in Pasty.

Preference layout rules:

- Use side-by-side controls for storage choices.
- Keep helper text aligned with the control it explains.
- Keep the full token reference in user docs.

The defaults carry the common workflow. Preferences are for artists whose workflow needs different storage or naming.
