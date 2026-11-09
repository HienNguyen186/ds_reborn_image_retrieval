"""Disk-cached gallery previews; original pixels remain available separately."""
import hashlib
import threading

from .catalog import load_image

_locks = [threading.Lock() for _ in range(32)]


def thumbnail_path(photo, index_root, size):
    key = hashlib.sha256(f"{photo.fingerprint}:{size}:jpeg82-v1".encode()).hexdigest()
    path = index_root / "thumbnails" / f"{key}.jpg"
    with _locks[int(key[:4], 16) % len(_locks)]:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            image = load_image(photo)
            image.thumbnail((size, size))
            temporary = path.with_suffix(".tmp")
            try:
                image.save(temporary, format="JPEG", quality=82)
                temporary.replace(path)
            finally:
                image.close()
                temporary.unlink(missing_ok=True)
    return path
