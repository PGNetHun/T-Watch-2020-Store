# Remove unused font files

import os
import sys
from pathlib import Path

_USAGE = """
Usage:

    python3 remove_unused_fonts.py [fonts_path] [search_path]

    [fonts_path]        Path of font files (example: "../fonts")
    [search_path]       Path to search for files containing font file names (example: "../")
    [skip_directories]  Comma separated list of directories to skip (relative to "search_path")

Script collects font file names, then searches for them in all ".py" and ".json" files.
"""

SEARCH_FILE_EXTENSIONS = [".py", ".json"]

try:
    fonts_dir = sys.argv[1]
    rootdir = sys.argv[2]
    skip_directories = list(map(lambda d: os.path.join(rootdir, d), sys.argv[3].split(','))) if len(sys.argv) > 3 else []
except:
    print(_USAGE)
    sys.exit(1)

font_files = [name for name in os.listdir(fonts_dir) if name.endswith(".font")]
used_font_files = []
original_font_files_count = len(font_files)

for currentdir, subdirs, files in os.walk(rootdir):
    # Skip directories we are not interested in
    if len([1 for skip_dir in skip_directories if skip_dir in currentdir]) > 0:
        continue

    for file_name in files:
        # Skip files we are not interested in
        if len([1 for extension in SEARCH_FILE_EXTENSIONS if file_name.endswith(extension)]) == 0:
            continue

        try:
            file_full_path = os.path.join(currentdir, file_name)
            file_content = Path(file_full_path).read_text()

            # Check for font file usage:
            used_font_files.extend([font_file for font_file in font_files if font_file in file_content])
        except Exception:
            print(f"Problem checking file: {file_full_path}")
            raise

        # Remove used fonts:
        for font_file in used_font_files:
            if font_file in font_files:
                font_files.remove(font_file)

unused_font_files_count = len(font_files)
used_font_files_count = len(used_font_files)
print(f"Font files count: {original_font_files_count}, used: {used_font_files_count}, NOT used: {unused_font_files_count}")
print("Remove NOT used fonts: ", font_files)

for font_file in font_files:
    os.remove(os.path.join(fonts_dir, font_file))
