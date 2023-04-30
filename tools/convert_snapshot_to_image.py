# Convert RAW snapshot file to PNG/JPEG image file

import sys
from PIL import Image

_USAGE = """
Usage:

  python3 convert_snapshot_to_image.py [rawfile] [imagefile] [width] [height]

    [rawfile]       Source snapshot RAW file (BGRA format)
    [imagefile]     Destination image file with extension (.png, .jpg, .webp)
    [width]         Width of image in pixels
    [height]        Height of image in pixels
"""

try:
    rawfile = sys.argv[1]
    imagefile = sys.argv[2]
    width = int(sys.argv[3])
    height = int(sys.argv[4])
except:
    print(_USAGE)
    sys.exit(1)

with open(rawfile, "rb") as f:
    rawData = f.read()

image = Image.frombuffer("RGBA", (width, height), rawData, "raw", "BGRA", 0, 1).convert("RGB")
image.save(imagefile, quality=90, optimize=True, progressive=False)
image.close()
