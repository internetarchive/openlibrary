#!/usr/bin/env python
"""
Utility script to be run on ol-home0 to convert some cover images from jpeg to webp.
It demonstrates how to:
1. read cover jpeg files from existing zip files on /1/var/tmp/imports,
2. how to get the size in bytes of image files,
3. convert jpeg images to webp

Sample output:
Cover filename      jpeg    webp    delta
-----------------  ------  ------  ------
9780000528742.jpg  13,252   8,534  64.40%
9780006499268.jpg  21,520  18,184  84.50%
9780006499305.jpg  20,648  17,552  85.01%
9780007217410.jpg  25,793  20,080  77.85%
9780007217427.jpg  30,450  24,568  80.68%
"""

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image

COVERS_DIR = "/1/var/tmp/imports/2022/covers/"


def main(debug: bool = False):
    """Convert all images in the current directory to webp."""
    with ZipFile(COVERS_DIR + "Apr2022_1_lc_13.zip") as in_file:
        for i, cover_file in enumerate(sorted(in_file.namelist())):
            if cover_file.endswith(".jpg"):
                image = Image.open(in_file.open(cover_file))
                with BytesIO() as jpeg_file:
                    image.save(jpeg_file, "jpeg")
                    src_image_size = jpeg_file.tell()
                with BytesIO() as webp_file:
                    image.save(webp_file, "webp")
                    dst_image_size = webp_file.tell()
                del image
                print(
                    f"{cover_file}  {src_image_size:,}  {dst_image_size:>6,}  "
                    f"{dst_image_size/src_image_size:.2%}"
                )
                if debug and i > 20:
                    break


if __name__ == "__main__":
    main(debug=True)
