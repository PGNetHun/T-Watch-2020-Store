# Generate faces list JSON and preview images

import json
import os
import sys
import subprocess

_USAGE = """
Usage:
    python3 generate.py [micropython executable]

    [micropython executable]    Path of Unix port MicroPython executable.
                                For example: "~/src/lv_micropython/ports/unix/micropython-dev"
"""

_LIST_FILE = "faces.txt"

_PREVIEW_TIME_CONSTANT = str((2023, 1, 1, 12, 0, 0, 0, 1))

_PREVIEWS_DIRECTORY = "_previews"
_PREVIEW_POSTFIX = "_preview"
_PREVIEW_EXTENSION = ".jpg"

_PYTHON_COMMAND = "python3"
_PREVIEW_MPY_FILE = "preview.py"

_SNAPSHOT_EXTENSION = ".raw"
_SNAPSHOT_CONVERTER = "../../tools/convert_snapshot_to_image.py"
_SNAPSHOT_WIDTH = 240
_SNAPSHOT_HEIGHT = 240

_THUMBNAIL_CONVERTER = "../../tools/resize_image.py"
_THUMBNAIL_WIDTH = 60
_THUMBNAIL_HEIGHT = 60
_THUMBNAIL_POSTFIX = "_thumbnail"
_THUMBNAIL_EXTENSION = ".jpg"

# Get MicroPython executable file path
try:
    mpy = sys.argv[1]
except:
    print(_USAGE)
    sys.exit(1)

# Save list of faces
face_names = [e.name for e in os.scandir(".") if e.is_dir() and not e.name.startswith("_")]
face_names.sort()
with open(_LIST_FILE, "w") as f:
    f.write("\n".join(face_names))

# Delete old orphan preview images
existing_files = set([e.name for e in os.scandir(_PREVIEWS_DIRECTORY) if e.is_file() and not e.name.startswith("_") and not e.name.startswith(".")])
keep_files = [f"{name}{_PREVIEW_POSTFIX}{_PREVIEW_EXTENSION}" for name in face_names]
keep_files.extend([f"{name}{_THUMBNAIL_POSTFIX}{_THUMBNAIL_EXTENSION}" for name in face_names])
for filename in existing_files.difference(keep_files):
    try:
        print(f"Delete unused files: {filename}")
        os.remove(f"{_PREVIEWS_DIRECTORY}/{filename}")
    except Exception as e:
        print(f"Error deleting old unused file: {filename}", e)

# Generate faces and take RAW snapshots
print("Take snapshots of faces")
subprocess.run([mpy, _PREVIEW_MPY_FILE, "--snapshot-for-all",_SNAPSHOT_EXTENSION, _PREVIEWS_DIRECTORY, _PREVIEW_TIME_CONSTANT])

# Convert snapshots to preview image and delete snapshot files
for name in face_names:
    print(f"Convert snapshot to preview image: {name}")

    snapshot_path = f"{_PREVIEWS_DIRECTORY}/{name}{_SNAPSHOT_EXTENSION}"
    preview_path = f"{_PREVIEWS_DIRECTORY}/{name}{_PREVIEW_POSTFIX}{_PREVIEW_EXTENSION}"
    thumbnail_path = f"{_PREVIEWS_DIRECTORY}/{name}{_THUMBNAIL_POSTFIX}{_THUMBNAIL_EXTENSION}"

    try:
        # Convert RAW snapshot to image preview file
        subprocess.run([_PYTHON_COMMAND, _SNAPSHOT_CONVERTER, snapshot_path, preview_path, str(_SNAPSHOT_WIDTH), str(_SNAPSHOT_HEIGHT)])

        # Create thumbnail image from preview file
        subprocess.run([_PYTHON_COMMAND, _THUMBNAIL_CONVERTER, preview_path, thumbnail_path, str(_THUMBNAIL_WIDTH), str(_THUMBNAIL_HEIGHT)])

        # Delete RAW file
        os.remove(snapshot_path)
    except Exception as e:
        print(f"Error converting face snapshot to preview image: {snapshot_path}", e)
