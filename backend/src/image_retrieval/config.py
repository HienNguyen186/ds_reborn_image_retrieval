from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, fields
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Config:
    data_root: Path = PROJECT_ROOT / "data"
    index_root: Path = PROJECT_ROOT / "artifacts" / "image_search"
    cache_root: Path = PROJECT_ROOT / "models"
    model_id: str = "google/siglip2-base-patch16-224"
    revision: str = "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2"
    device: str = "auto"
    precision: str = "auto"
    batch_size: int = 4
    region_mode: str = "grid"
    local_files_only: bool = False
    preload_model: bool = False

    def __post_init__(self):
        for key in ("data_root", "index_root", "cache_root"):
            object.__setattr__(self, key, Path(getattr(self, key)).resolve())
        if self.region_mode not in {"none", "grid"}:
            raise ValueError("region_mode must be 'none' or 'grid'")
        if self.device not in {"auto", "cpu", "cuda"}:
            raise ValueError("device must be auto, cpu or cuda")
        if self.precision not in {"auto", "fp32", "fp16"}:
            raise ValueError("precision must be auto, fp32 or fp16")
        if not 1 <= self.batch_size <= 128:
            raise ValueError("batch_size must be between 1 and 128")

    @property
    def signature(self) -> str:
        # Change the version when preprocessing or region geometry changes.
        payload = {"format": 1, "model": self.model_id, "revision": self.revision,
                   "regions": self.region_mode, "preprocess": "siglip-processor-exif-rgb-v1",
                   "precision": self.precision}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def load_config(path: str | Path | None = None) -> Config:
    path = Path(path or os.environ.get("IMAGE_SEARCH_CONFIG", PROJECT_ROOT / "backend/configs/images.json"))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    unknown = set(values) - {f.name for f in fields(Config)}
    if unknown:
        raise ValueError(f"Unknown image search settings: {sorted(unknown)}")
    for key in ("data_root", "index_root", "cache_root"):
        if key in values and not Path(values[key]).is_absolute():
            values[key] = PROJECT_ROOT / values[key]
    return Config(**values)
