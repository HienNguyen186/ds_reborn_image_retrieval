from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageOps

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class Photo:
    image_id: str
    path: Path
    width: int
    height: int
    size: int
    mtime_ns: int
    error: str = ""

    @property
    def batch(self):
        parts = self.image_id.split("/")
        return parts[0] if len(parts) > 1 else "root"

    @property
    def fingerprint(self):
        return [self.image_id, self.size, self.mtime_ns]

    def public(self):
        return {"image_id": self.image_id, "filename": self.path.name, "batch": self.batch,
                "image_url": "/api/image/" + quote(self.image_id, safe="/"),
                "thumbnail_url": "/api/image/" + quote(self.image_id, safe="/") + f"?size=640&v={self.mtime_ns}",
                "width": self.width, "height": self.height}


class Catalog:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.photos = []
        if self.root.is_dir():
            for path in sorted(self.root.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
                    continue
                if not path.resolve().is_relative_to(self.root):
                    continue
                stat = path.stat()
                error, width, height = "", 0, 0
                try:
                    with Image.open(path) as image:
                        width, height = image.size
                        if image.getexif().get(274, 1) in {5, 6, 7, 8}:
                            width, height = height, width
                        image.verify()
                except (OSError, ValueError, Image.DecompressionBombError) as exc:
                    error = str(exc)
                self.photos.append(Photo(path.relative_to(self.root).as_posix(), path,
                                         width, height, stat.st_size, stat.st_mtime_ns, error))
        self.by_id = {p.image_id: p for p in self.photos}
        self.fingerprint = hashlib.sha256(json.dumps(
            [p.fingerprint for p in self.photos], ensure_ascii=False).encode()).hexdigest()
        self.batches = [{"name": name, "count": count}
                        for name, count in sorted(Counter(p.batch for p in self.photos).items())]


def load_image(photo: Photo) -> Image.Image:
    with Image.open(photo.path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def image_regions(image: Image.Image, mode: str):
    """Full frame plus overlapping quadrants, in EXIF-corrected pixels.

    Fixed regions need no extra detector/checkpoint. They are NOT person
    detections and their labels should not be presented as detected objects.
    """
    width, height = image.size
    regions = [{"label": "full", "bbox": [0, 0, width, height]}]
    if mode == "grid":
        for name, x1, y1, x2, y2 in (
            ("top_left", 0, 0, .65, .65), ("top_right", .35, 0, 1, .65),
            ("bottom_left", 0, .35, .65, 1), ("bottom_right", .35, .35, 1, 1),
        ):
            box = [int(x1 * width), int(y1 * height), max(1, int(x2 * width)), max(1, int(y2 * height))]
            regions.append({"label": name, "bbox": box})
    return [image.crop(region["bbox"]) for region in regions], regions
