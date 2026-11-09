"""Compatibility boundary for the unchanged video-oriented React frontend.

The historical names video_id/frame_id are used as image group/identifier
only. The source provides no video files, frame rates or verified timestamps.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

MODEL_KEY = "siglip2"


class LegacyOptions(BaseModel):
    dataset: str = "aic"
    video_ids: list[str] = Field(default_factory=list, max_length=500)
    model_key: str | None = None

    @field_validator("dataset")
    @classmethod
    def dataset_alias(cls, value):
        if value.lower() not in {"aic", "cam"}:
            raise ValueError("dataset phải là aic hoặc cam (alias cho cùng bộ ảnh hiện tại).")
        return value.lower()

    @field_validator("model_key")
    @classmethod
    def known_model(cls, value):
        if value and value != MODEL_KEY:
            raise ValueError(f"Model không tồn tại. Chọn {MODEL_KEY}.")
        return value or MODEL_KEY


class LegacySimilarityRequest(LegacyOptions):
    video_id: str
    frame_id: int
    top_k: int = Field(default=20, ge=1, le=500)
    use_regions: bool = True


def identity(photo):
    path = PurePosixPath(photo.image_id)
    prefix, separator, suffix = path.stem.rpartition("_")
    if separator and prefix and suffix.isdigit():
        return str(path.parent / prefix), int(suffix)
    # Stable JS-safe integer for files without a numeric suffix. Do not invent
    # a frame number by assuming a position in a source video.
    return str(path.parent), int(hashlib.sha256(photo.image_id.encode()).hexdigest()[:12], 16)


class LegacyAdapter:
    def __init__(self, service):
        self.service = service
        self.fingerprint = None
        self.groups = {}
        self.lookup = {}
        self._refresh()

    def _refresh(self):
        catalog = self.service.catalog
        if self.fingerprint == catalog.fingerprint:
            return
        groups, lookup = {}, {}
        for photo in catalog.photos:
            group, number = identity(photo)
            groups.setdefault(group, []).append(photo)
            lookup.setdefault((group, number), []).append(photo)
        for photos in groups.values():
            photos.sort(key=lambda photo: (identity(photo)[1], photo.image_id))
        self.groups, self.lookup, self.fingerprint = groups, lookup, catalog.fingerprint

    def filter_ids(self, video_ids):
        self._refresh()
        if not video_ids:
            return None
        missing = set(video_ids) - set(self.groups)
        if missing:
            raise ValueError("Nhóm ảnh không tồn tại: " + ", ".join(sorted(missing)))
        return {photo.image_id for group in video_ids for photo in self.groups[group]}

    def find(self, video_id, frame_id):
        self._refresh()
        matches = self.lookup.get((video_id, frame_id), [])
        if not matches:
            raise KeyError((video_id, frame_id))
        if len(matches) != 1:
            raise ValueError("Mã ảnh không duy nhất; dùng image_id đầy đủ qua /api/image.")
        return matches[0]

    def result(self, item, dataset="aic", rank=1, search_mode="semantic"):
        photo = self.service.catalog.by_id[item["image_id"]]
        group, number = identity(photo)
        raw = {"image_id": photo.image_id, "filename": photo.path.name, "batch": photo.batch,
               "video_id": group, "keyframe_id": number, "keyframe_id_int": number,
               "frame_idx": None, "timestamp_sec": None, "fps": None,
               "identifier_source": "filename_suffix", "model_key": MODEL_KEY,
               "dataset": dataset, "collection": dataset}
        return {**item, "id": photo.image_id, "video_id": group, "frame_id": number,
                "keyframe_id": number, "frame_idx": None, "frame_name": photo.path.name,
                "path": photo.image_id, "keyframe_path": photo.image_id,
                # Empty relative path bypasses legacy VITE_* remote video-asset bases.
                "image_rel_path": "", "video_rel_path": "", "map_rel_path": "",
                "video_url": "", "map_url": "", "timestamp": None, "fps": None,
                "similarity": item.get("score", 0.0), "rank": rank,
                "collection": dataset, "dataset": dataset, "model_key": MODEL_KEY,
                "search_mode": search_mode, "matched_sequence": [], "raw": raw}

    def response(self, payload, dataset="aic", search_mode="semantic"):
        results = [self.result(item, dataset, rank, search_mode)
                   for rank, item in enumerate(payload["results"], 1)]
        return {**payload, "results": results, "count": len(results), "model_key": MODEL_KEY,
                "latency_ms": payload["elapsed_ms"], "search_mode": search_mode,
                "original_query": payload["query"], "translated_query": None,
                "use_translate": False, "use_split": bool(payload.get("sub_queries")),
                "sub_queries": payload.get("sub_queries", []),
                "events": [], "event_queries": [], "duration_limit": -1}


def check_mode(mode, query=""):
    if mode not in {"semantic", "auto", "fusion"} or re.search(r"\bTHEN\b", query):
        raise HTTPException(501, "Bộ dữ liệu hiện chỉ có ảnh tĩnh. Dùng Semantic/Auto; chưa có video, thứ tự thời gian, OCR hoặc ASR.")


def make_router(run_search):
    router = APIRouter(tags=["original-frontend"])

    def adapter(request):
        return request.app.state.legacy

    def check_dataset(dataset):
        if dataset.lower() not in {"aic", "cam"}:
            raise HTTPException(422, "dataset phải là aic hoặc cam.")
        return dataset.lower()

    def model_info(service):
        return {"key": MODEL_KEY, "name": service.config.model_id, "pretrained": service.config.revision,
                "device": service.status()["device"], "precision": service.config.precision, "normalize": True}

    @router.get("/api/health")
    def health(request: Request):
        service = request.app.state.service
        return {**service.status(), "status": "ok", "model": model_info(service),
                "available_models": [MODEL_KEY], "semantic_model_roles": {"local": MODEL_KEY, "global": MODEL_KEY},
                "ocr": {"available": False}, "asr": {"available": False}}

    @router.get("/api/config")
    def public_config(request: Request):
        return {"datasets": {"default": "aic", "available": [
                    {"key": key, "label": f"{key.upper()} · data/Batch* (cùng bộ ảnh)"} for key in ("aic", "cam")]},
                "search": {"default_top_k": 60, "max_top_k": 500, "candidate_multiplier": 1,
                           "available_modes": ["semantic", "auto", "fusion"], "default_search_mode": "semantic",
                           "default_duration_limit": -1, "default_model_key": MODEL_KEY},
                "ui": {"surrounding_radius": 5, "max_surrounding_radius": 20},
                "translate": {"enabled_default": False, "provider": "native_multilingual", "source": "vi", "target": "vi"},
                "model": model_info(request.app.state.service), "available_models": [MODEL_KEY],
                "semantic_model_roles": {"local": MODEL_KEY, "global": MODEL_KEY},
                "ocr": {"available": False}, "asr": {"available": False},
                "capabilities": {"still_images": True, "video": False, "timestamps": False,
                                 "index_ready": request.app.state.service.index_ready}}

    @router.get("/api/search/models")
    def models(dataset: str = "aic"):
        check_dataset(dataset)
        return {"models": [MODEL_KEY], "default_model_key": MODEL_KEY}

    @router.get("/api/video-ids")
    def video_ids(request: Request, dataset: str = "aic"):
        check_dataset(dataset)
        legacy = adapter(request)
        legacy._refresh()
        return {"video_ids": sorted(legacy.groups), "kind": "image_filename_groups"}

    @router.get("/api/frame-info")
    def frame_info(request: Request, video_id: str, keyframe_id: int | None = None,
                   frame_id: int | None = None, dataset: str = "aic", timestamp_ms: float | None = None):
        dataset = check_dataset(dataset)
        if keyframe_id is None and frame_id is None:
            raise HTTPException(422, "Cần keyframe_id từ tên ảnh; không thể suy ra ảnh từ timestamp khi thiếu video/FPS.")
        legacy = adapter(request)
        def resolve():
            photo = legacy.find(video_id, keyframe_id if keyframe_id is not None else frame_id)
            return legacy.result(photo.public(), dataset)
        return run_search(resolve)

    @router.get("/api/surrounding-frames")
    def surrounding(request: Request, video_id: str, keyframe_id: int, dataset: str = "aic",
                    radius: int = Query(5, ge=0, le=20)):
        dataset = check_dataset(dataset)
        legacy = adapter(request)
        def resolve():
            photo = legacy.find(video_id, keyframe_id)
            photos = legacy.groups[video_id]
            center = next(index for index, item in enumerate(photos) if item.image_id == photo.image_id)
            frames = [legacy.result(item.public(), dataset, rank)
                      for rank, item in enumerate(photos[max(0, center-radius):center+radius+1], 1)]
            return {"frames": frames, "video_id": video_id, "keyframe_id": keyframe_id,
                    "ordering": "filename_numeric_suffix", "temporal": False}
        return run_search(resolve)

    @router.post("/api/similarity-search")
    def similarity(request: Request, payload: LegacySimilarityRequest):
        legacy = adapter(request)
        def resolve():
            photo = legacy.find(payload.video_id, payload.frame_id)
            response = legacy.service.similar(photo.image_id, payload.top_k, use_regions=payload.use_regions,
                                               image_ids=legacy.filter_ids(payload.video_ids))
            return {**legacy.response(response, payload.dataset, "similarity"),
                    "source": legacy.result(photo.public(), payload.dataset)}
        return run_search(resolve)

    @router.post("/api/search/fusion")
    def fusion(request: Request, payload: dict):
        check_dataset(str(payload.get("dataset", "aic")))
        if payload.get("temporal") or payload.get("use_ocr") or payload.get("use_asr"):
            raise HTTPException(501, "Fusion hiện chỉ hỗ trợ semantic trên ảnh; chưa có nguồn temporal/OCR/ASR.")
        if set(payload.get("semantic_models") or [MODEL_KEY]) != {MODEL_KEY}:
            raise HTTPException(422, f"Chỉ có model {MODEL_KEY} trong bộ index hiện tại.")
        # Reuse the validated search endpoint so top_k, query and filters have
        # exactly the same validation as /api/search (no silent coercion).
        return run_search(request.app.state.compat_search, payload={**payload, "search_mode": "fusion"})

    @router.get("/api/video-keyframes")
    @router.get("/api/video-preview")
    def no_video():
        raise HTTPException(501, "Không có video/FPS để dựng timeline từ bộ ảnh này.")

    @router.post("/api/rerank")
    @router.post("/api/speech/transcribe")
    def unavailable():
        raise HTTPException(501, "Chức năng này chưa được cấu hình cho bộ ảnh hiện tại. Dùng tìm kiếm Semantic hoặc Similar.")

    return router
