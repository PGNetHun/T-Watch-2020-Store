# Resize image

import sys
from PIL import Image

_USAGE = """
Usage:

  python3 resize_image.py [source] [destination] [width] [height]

    [source]        Source image file
    [destination]   Destination image file
    [width]         New width in pixels
    [height]        New height in pixels

Supported file formats: .png, .jpg, .webp
"""

try:
    source = sys.argv[1]
    destination = sys.argv[2]
    width = int(sys.argv[3])
    height = int(sys.argv[4])
except:
    print(_USAGE)
    sys.exit(1)

with Image.open(source, mode="r") as image:
    resized = image.resize((width, height))
    resized.save(destination, quality=90, optimize=True, progressive=False)
