# Generate faces list JSON and preview images

import os
import sys
import subprocess

from PIL import Image

_USAGE = """
Usage:
    python3 generate.py [micropython executable] [faces directory]

    [micropython executable]    Path of Unix port MicroPython executable.
                                For example: "~/src/lv_micropython/ports/unix/build-standard/micropython"
    [faces directory]           Path of faces directory. Optional.
"""

_LIST_FILE = "faces.txt"

_PREVIEW_TIME_CONSTANT = str((2023, 1, 1, 10, 10, 0, 0, 1))
_PREVIEW_MPY_FILE = "preview.py"

_PREVIEWS_DIRECTORY = "_previews"
_PREVIEW_NAME_FORMAT = "{}_preview.jpg"
_THUMBNAIL_NAME_FORMAT = "{}_thumbnail.jpg"
_SNAPSHOT_EXTENSION = ".raw"

_SNAPSHOT_WIDTH = 240
_SNAPSHOT_HEIGHT = 240

_THUMBNAIL_WIDTH = 60
_THUMBNAIL_HEIGHT = 60

_JPEG_SNAPSHOT_QUALITY = 85
_JPEG_THUMBNAIL_QUALITY = 85
_JPEG_PROGRESSIVE = False

# Get MicroPython executable file path
try:
    mpy = sys.argv[1]
    path = sys.argv[2] if len(sys.argv) > 2 else "."
except:
    print(_USAGE)
    sys.exit(1)

# Save list of faces
face_names = [e.name for e in os.scandir(path) if e.is_dir() and not e.name.startswith("_")]
face_names.sort()
with open(_LIST_FILE, "w") as f:
    f.write("\n".join(face_names))

# Delete old orphan images
existing_files = set([e.name for e in os.scandir(_PREVIEWS_DIRECTORY) if e.is_file() and not e.name.startswith("_") and not e.name.startswith(".")])
keep_files = [_PREVIEW_NAME_FORMAT.format(name) for name in face_names]
keep_files.extend([_THUMBNAIL_NAME_FORMAT.format(name) for name in face_names])

for filename in existing_files.difference(keep_files):
    try:
        print(f"Delete unused files: {filename}")
        os.remove(f"{_PREVIEWS_DIRECTORY}/{filename}")
    except Exception as e:
        print(f"Error deleting old unused file: {filename}", e)

# Generate faces and take RAW snapshots
print("Take snapshots of faces")
subprocess.run([mpy, _PREVIEW_MPY_FILE, "--snapshot-for-all", _SNAPSHOT_EXTENSION, _PREVIEWS_DIRECTORY, _PREVIEW_TIME_CONSTANT])

# Convert snapshots to preview image and delete snapshot files
for name in face_names:
    print(f"Convert snapshot to preview image: {name}")

    snapshot_path = f"{_PREVIEWS_DIRECTORY}/{name}{_SNAPSHOT_EXTENSION}"
    preview_path = f"{_PREVIEWS_DIRECTORY}/{_PREVIEW_NAME_FORMAT.format(name)}"
    thumbnail_path = f"{_PREVIEWS_DIRECTORY}/{_THUMBNAIL_NAME_FORMAT.format(name)}"

    try:
        # Convert RAW snapshot to image preview file
        with open(snapshot_path, "rb") as f:
            rawData = f.read()
            image = Image.frombuffer("RGBA", (_SNAPSHOT_WIDTH, _SNAPSHOT_HEIGHT), rawData, "raw", "BGRA", 0, 1).convert("RGB")
            image.save(preview_path, quality=_JPEG_SNAPSHOT_QUALITY, optimize=True, subsampling=2, progressive=_JPEG_PROGRESSIVE)
            image.close()

        # Create thumbnail image from preview file
        with Image.open(preview_path, mode="r") as image:
            resized = image.resize((_THUMBNAIL_WIDTH, _THUMBNAIL_HEIGHT))
            resized.save(thumbnail_path, quality=_JPEG_THUMBNAIL_QUALITY, optimize=True, subsampling=2, progressive=_JPEG_PROGRESSIVE)

        # Delete RAW file
        os.remove(snapshot_path)
    except Exception as e:
        print(
            f"Error converting face snapshot to preview image: {snapshot_path}", e)
