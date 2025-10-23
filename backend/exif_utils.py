from PIL import Image
from PIL.ExifTags import TAGS
import os

def extract_exif(path):
    """Extract EXIF metadata from an image file, returns a dict."""
    if not os.path.isfile(path):
        return {}

    try:
        img = Image.open(path)
        exifdata = img.getexif()
        if not exifdata:
            return {}

        readable = {}
        for tag_id, value in exifdata.items():
            tag = TAGS.get(tag_id, tag_id)
            readable[tag] = value

        return readable
    except Exception:
        return {}
