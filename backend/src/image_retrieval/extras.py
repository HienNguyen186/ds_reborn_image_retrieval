"""Image-only color and attachment search for the unchanged frontend."""
from __future__ import annotations

import io
import threading
import time

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageOps
from pydantic import BaseModel, Field, field_validator

from src.color_retrieval.palette import COLOR_NAMES, palette_indices

from .catalog import load_image
from .legacy import LegacyOptions, check_mode
from .service import atomic_npz, normalize

MAX_UPLOAD_BYTES = 8 * 1024 * 1024


class ColorCell(BaseModel):
    row: int = Field(ge=0, le=4)
    col: int = Field(ge=0, le=4)
    color: str

    @field_validator("color")
    @classmethod
    def known_color(cls, value):
        if value not in COLOR_NAMES:
            raise ValueError("Màu không tồn tại trong bảng màu 11 màu.")
        return value


class ColorRequest(LegacyOptions):
    cells: list[ColorCell] = Field(min_length=1, max_length=25)
    top_k: int = Field(default=20, ge=1, le=500)

    @field_validator("cells")
    @classmethod
    def distinct_cells(cls, cells):
        if len({(cell.row, cell.col) for cell in cells}) != len(cells):
            raise ValueError("Mỗi ô chỉ được chọn một màu.")
        return cells


class Clause(BaseModel):
    text: str = Field(default="", max_length=4000)
    image_indices: list[int] = Field(default_factory=list, max_length=8)
    connector_before: str | None = None

    @field_validator("connector_before")
    @classmethod
    def valid_connector(cls, value):
        if value not in {None, "AND", "THEN"}:
            raise ValueError("Mệnh đề chỉ hỗ trợ AND hoặc THEN.")
        return value


class MultimodalRequest(LegacyOptions):
    query: str = Field(default="", max_length=4000)
    clauses: list[Clause] = Field(default_factory=list, max_length=16)
    top_k: int = Field(default=20, ge=1, le=500)
    search_mode: str = "semantic"
    use_regions: bool = True


def color_grid(image):
    """Same equal-area 5×5 dominant-palette geometry as the original UI."""
    sampled = image.resize((50, 50), Image.Resampling.BOX)
    labels = palette_indices(np.asarray(sampled, dtype=np.uint8))
    return np.asarray([
        np.bincount(labels[row * 10:(row + 1) * 10, col * 10:(col + 1) * 10].ravel(),
                    minlength=len(COLOR_NAMES)).argmax()
        for row in range(5) for col in range(5)
    ], dtype=np.uint8)


class ColorCache:
    def __init__(self, service):
        self.service = service
        self.lock = threading.Lock()
        self.fingerprint = None
        self.grids = None
        self.photos = None

    def get(self):
        with self.lock:
            catalog = self.service.catalog
            if self.fingerprint == catalog.fingerprint:
                return self.photos, self.grids
            path = self.service.config.index_root / "color_grid.npz"
            grids = None
            if path.exists():
                try:
                    with np.load(path, allow_pickle=False) as data:
                        if str(data["fingerprint"].item()) == catalog.fingerprint:
                            candidate = data["grids"]
                            if candidate.shape == (len(catalog.photos), 25) and candidate.dtype == np.uint8 and np.all(candidate < len(COLOR_NAMES)):
                                grids = candidate
                except (OSError, ValueError, KeyError):
                    pass
            if grids is None:
                damaged = [photo.image_id for photo in catalog.photos if photo.error]
                if damaged:
                    raise ValueError("Có ảnh lỗi cần sửa trước khi tìm màu: " + ", ".join(damaged[:3]))
                grids = np.asarray([color_grid(load_image(photo)) for photo in catalog.photos], dtype=np.uint8).reshape(-1, 25)
                if self.service.catalog.fingerprint != catalog.fingerprint:
                    raise ValueError("Danh sách ảnh vừa thay đổi; hãy tìm màu lại.")
                atomic_npz(path, fingerprint=catalog.fingerprint, grids=grids)
            self.fingerprint, self.grids, self.photos = catalog.fingerprint, grids, catalog.photos
            return self.photos, self.grids


def make_router(run_search):
    router = APIRouter(tags=["image-search-extras"])
    initialization_lock = threading.Lock()

    @router.post("/api/search/color")
    def search_color(request: Request, payload: ColorRequest):
        def execute():
            started = time.perf_counter()
            service = request.app.state.service
            legacy = request.app.state.legacy
            allowed_ids = legacy.filter_ids(payload.video_ids)
            with initialization_lock:
                if not hasattr(service, "_color_cache"):
                    service._color_cache = ColorCache(service)
            photos, grids = service._color_cache.get()
            positions = [cell.row * 5 + cell.col for cell in payload.cells]
            colors = np.asarray([COLOR_NAMES.index(cell.color) for cell in payload.cells])
            scores = (grids[:, positions] == colors).mean(axis=1)
            candidates = [{**photo.public(), "score": round(float(score), 6)}
                          for photo, score in zip(photos, scores)
                          if allowed_ids is None or photo.image_id in allowed_ids]
            candidates.sort(key=lambda item: (-item["score"], item["image_id"]))
            return legacy.response({
                "results": candidates[:payload.top_k], "query": "Dominant color search",
                "total": len(candidates), "elapsed_ms": round((time.perf_counter()-started)*1000, 1),
            }, payload.dataset, "color")
        return run_search(execute)

    @router.post("/api/search/multimodal")
    async def search_multimodal(request: Request, request_json: str = Form(...),
                                images: list[UploadFile] = File(default=[])):
        decoded = []
        try:
            try:
                payload = MultimodalRequest.model_validate_json(request_json)
            except ValueError as exc:
                raise HTTPException(422, f"Metadata truy vấn không hợp lệ: {exc}") from exc
            check_mode(payload.search_mode, payload.query)
            if any(clause.connector_before == "THEN" for clause in payload.clauses):
                raise HTTPException(501, "Ảnh tĩnh không cung cấp thứ tự thời gian cho THEN.")
            if len(images) > 8:
                raise HTTPException(413, "Tối đa 8 ảnh mẫu trong một truy vấn.")
            for image in images:
                data = await image.read(MAX_UPLOAD_BYTES + 1)
                if len(data) > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Mỗi ảnh mẫu không được vượt quá 8 MB.")
                try:
                    with Image.open(io.BytesIO(data)) as source:
                        if source.width * source.height > 25_000_000:
                            raise HTTPException(413, "Ảnh mẫu không được vượt quá 25 triệu pixel.")
                        decoded.append(ImageOps.exif_transpose(source).convert("RGB"))
                except (OSError, ValueError, Image.DecompressionBombError) as exc:
                    raise HTTPException(422, "File đính kèm không phải ảnh hợp lệ.") from exc
            for clause in payload.clauses:
                if any(index < 0 or index >= len(decoded) for index in clause.image_indices):
                    raise HTTPException(422, "Chỉ số ảnh trong mệnh đề không hợp lệ.")
            check_mode(payload.search_mode, " ".join(clause.text for clause in payload.clauses))
            text_values = [clause.text.strip() for clause in payload.clauses if clause.text.strip()]
            if not text_values and payload.query.strip():
                text_values = [payload.query.strip()]
            image_indices = sorted({index for clause in payload.clauses for index in clause.image_indices})
            if not payload.clauses:
                image_indices = list(range(len(decoded)))
            if not text_values and not image_indices:
                raise HTTPException(422, "Cần ít nhất một mô tả hoặc một ảnh mẫu.")

            def execute():
                started = time.perf_counter()
                service = request.app.state.service
                legacy = request.app.state.legacy
                allowed_ids = legacy.filter_ids(payload.video_ids)
                store, catalog = service._ready_store()
                vectors, truncated = [], False
                with service._encoder_lock:
                    encoder = service._get_encoder()
                    for text in text_values:
                        vectors.append(normalize(encoder.encode_text(text)))
                        truncated = truncated or getattr(encoder, "last_query_truncated", False)
                    if image_indices:
                        vectors.append(normalize(encoder.encode_images([decoded[index] for index in image_indices])))
                # All inputs share the same paired encoder. Each input receives
                # equal weight; no text-only embedding space is mixed into it.
                query_vector = normalize(np.concatenate(vectors, axis=0).mean(axis=0))
                results, total = service._rank(store, catalog, query_vector, payload.top_k, [],
                                               payload.use_regions, image_ids=allowed_ids)
                response = legacy.response({
                    "results": results, "query": payload.query.strip() or " AND ".join(text_values) or "Image query",
                    "total": total, "elapsed_ms": round((time.perf_counter()-started)*1000, 1),
                }, payload.dataset, payload.search_mode)
                response["warnings"] = ["Mô tả vượt giới hạn token của model; hãy rút gọn."] if truncated else []
                return response
            return await run_in_threadpool(run_search, execute)
        finally:
            for image in images:
                await image.close()
            for image in decoded:
                image.close()

    return router
