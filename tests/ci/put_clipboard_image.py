import base64
import platform
import subprocess
import tempfile
from pathlib import Path

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lG/e0gAAAABJRU5ErkJggg=="
)


def main() -> None:
    system = platform.system()
    image_path = Path(tempfile.gettempdir()) / "pasty-ci-clipboard.png"
    image_path.write_bytes(PNG_BYTES)

    if system == "Darwin":
        put_macos(image_path)
    elif system == "Windows":
        put_windows(image_path)
    elif system == "Linux":
        put_linux()
    else:
        msg = f"unsupported clipboard platform: {system}"
        raise RuntimeError(msg)

    print(f"clipboard image: {image_path}")


def put_macos(image_path: Path) -> None:
    command = f'set the clipboard to (read file POSIX file "{image_path}" as «class PNGf»)'
    subprocess.run(["osascript", "-e", command], check=True)


def put_windows(image_path: Path) -> None:
    script = rf"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$image = [System.Drawing.Image]::FromFile('{image_path}')
$data = New-Object System.Windows.Forms.DataObject
$data.SetData([System.Windows.Forms.DataFormats]::Bitmap, $true, $image)
[System.Windows.Forms.Clipboard]::SetDataObject($data, $true)
$image.Dispose()
"""
    subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", script], check=True)


def put_linux() -> None:
    subprocess.run(["wl-copy", "--type", "image/png"], input=PNG_BYTES, check=True)
    subprocess.run(["wl-paste", "--list-types"], check=True)


if __name__ == "__main__":
    main()
