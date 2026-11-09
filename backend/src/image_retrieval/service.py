from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
from pathlib import Path

import numpy as np

from .catalog import Catalog, image_regions, load_image
from .config import Config
from .encoder import SiglipEncoder

logger = logging.getLogger(__name__)


class IndexNotReady(RuntimeError):
    pass


def normalize(vectors):
    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.ndim == 1:
        vectors = vectors.reshape(1, -1)
    if vectors.ndim != 2 or vectors.shape[1] == 0 or not np.isfinite(vectors).all():
        raise ValueError("Embedding phải là ma trận hữu hạn hai chiều.")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms < 1e-12):
        raise ValueError("Encoder trả về vector rỗng (zero vector).")
    return np.ascontiguousarray(vectors / norms)


def atomic_npz(path: Path, **arrays):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as stream:
            np.savez(stream, **arrays)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class VectorStore:
    def __init__(self, vectors, records, metadata):
        self.vectors = normalize(vectors)
        if len(self.vectors) != len(records):
            raise ValueError("Index vector/metadata length mismatch.")
        self.records = records
        self.metadata = metadata
        self.rows_by_id = {}
        for row, record in enumerate(records):
            self.rows_by_id.setdefault(record["image_id"], []).append(row)
        # Precompute grouping once; avoid sorting all region vectors per query.
        self.image_ids = sorted(self.rows_by_id)
        self.id_array = np.asarray(self.image_ids)
        self.full_rows = np.asarray([next(row for row in self.rows_by_id[key]
                                          if records[row]["label"] == "full") for key in self.image_ids])
        width = max(len(rows) for rows in self.rows_by_id.values())
        self.region_rows = np.empty((len(self.image_ids), width), dtype=np.intp)
        for index, key in enumerate(self.image_ids):
            rows = self.rows_by_id[key]
            self.region_rows[index] = rows + [int(self.full_rows[index])] * (width-len(rows))
        self.faiss = None

    def score_matrix(self, queries):
        queries = normalize(queries)
        if queries.shape[1] != self.vectors.shape[1]:
            raise ValueError("Query/index dimensions differ. Build lại index với đúng model.")
        return (self.vectors @ queries.T).T

    def scores(self, query):
        query = normalize(query)
        if query.shape != (1, self.vectors.shape[1]):
            raise ValueError("Query/index dimensions differ. Build lại index với đúng model.")
        return self.score_matrix(query)[0]


class ImageSearchService:
    def __init__(self, config: Config, encoder_factory=None):
        self.config = config
        self.catalog = Catalog(config.data_root)
        self._encoder_factory = encoder_factory or SiglipEncoder
        self._encoder = None
        self._encoder_lock = threading.Lock()
        self._text_cache = OrderedDict()
        self.model_error = ""
        self._state_lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="image-index")
        self._stop = threading.Event()
        self.store = None
        self.error = ""
        self.build = {"state": "idle", "processed": 0, "total": len(self.catalog.photos), "message": ""}
        self._load_index()

    def _load_index(self):
        path = self.config.index_root / "index.npz"
        if not path.exists():
            return
        try:
            with np.load(path, allow_pickle=False) as data:
                metadata = json.loads(str(data["metadata"].item()))
                if metadata.get("signature") != self.config.signature:
                    raise ValueError("Cấu hình embedding đã đổi. Hãy tạo lại index.")
                if metadata.get("dataset") != self.catalog.fingerprint:
                    raise ValueError("Dữ liệu đã thay đổi. Hãy cập nhật index.")
                records = json.loads(str(data["records"].item()))
                store = VectorStore(data["vectors"], records, metadata)
            if set(store.rows_by_id) != set(self.catalog.by_id):
                raise ValueError("Index không khớp danh sách ảnh. Hãy tạo lại index.")
            self.store = store
        except Exception as exc:
            self.error = f"Không đọc được index: {exc}"
            logger.warning(self.error)

    @property
    def index_ready(self):
        return self.store is not None and self.store.metadata.get("dataset") == self.catalog.fingerprint

    def status(self):
        with self._state_lock:
            return {
                "image_count": len(self.catalog.photos),
                "indexed_images": len(self.store.rows_by_id) if self.index_ready else 0,
                "index_ready": self.index_ready,
                "model_id": self.config.model_id,
                "device": str(self._encoder.device) if self._encoder is not None else self.config.device,
                "region_mode": self.config.region_mode,
                "batches": self.catalog.batches,
                "build": dict(self.build),
                "error": self.error or None,
                "catalog_errors": [{"image_id": p.image_id, "error": p.error}
                                   for p in self.catalog.photos if p.error],
                "search_engine": "numpy-exact",
                "model_ready": self._encoder is not None,
                "model_error": self.model_error or None,
            }

    def _get_encoder(self):
        if self._encoder is None:
            self._encoder = self._encoder_factory(self.config)
        return self._encoder

    def _encode_cached(self, encoder, text):
        key = text.strip()
        if key in self._text_cache:
            self._text_cache.move_to_end(key)
            return self._text_cache[key]
        value = (normalize(encoder.encode_text(key)), getattr(encoder, "last_query_truncated", False))
        self._text_cache[key] = value
        if len(self._text_cache) > 256:
            self._text_cache.popitem(last=False)
        return value

    def prepare(self):
        """Load and warm the model before accepting HTTP searches."""
        try:
            with self._encoder_lock:
                self._encode_cached(self._get_encoder(), "người trong bếp")
            self.model_error = ""
        except Exception as exc:
            self.model_error = str(exc)
            logger.warning("Model warmup failed: %s", type(exc).__name__)

    def start_build(self, rebuild=False):
        with self._state_lock:
            if self.build["state"] == "running":
                return self.status()
            self.error = ""
            self.build = {"state": "running", "processed": 0, "total": len(self.catalog.photos),
                          "message": "Đang kiểm tra dữ liệu và nạp model (lần đầu cần tải checkpoint)…"}
            self._executor.submit(self._build, rebuild)
            return self.status()

    def _progress(self, **values):
        with self._state_lock:
            self.build.update(values)

    def _build(self, rebuild):
        try:
            catalog = Catalog(self.config.data_root)
            with self._state_lock:
                self.catalog = catalog
                self.build["total"] = len(catalog.photos)
            if not catalog.photos:
                raise ValueError(f"Không tìm thấy ảnh tại {self.config.data_root}")
            damaged = [p.image_id for p in catalog.photos if p.error]
            if damaged:
                raise ValueError(f"Có {len(damaged)} ảnh lỗi, ví dụ: {', '.join(damaged[:3])}. Sửa ảnh trước khi tạo index.")
            cache_dir = self.config.index_root / "cache" / self.config.signature
            records, chunks = [], []
            for number, photo in enumerate(catalog.photos, start=1):
                if self._stop.is_set():
                    raise RuntimeError("Đã dừng tạo index. Cache đã tạo được giữ để tiếp tục lần sau.")
                key = hashlib.sha256(json.dumps(photo.fingerprint).encode()).hexdigest()
                cache_path = cache_dir / f"{key}.npz"
                vectors, regions = None, None
                if cache_path.exists() and not rebuild:
                    try:
                        with np.load(cache_path, allow_pickle=False) as data:
                            vectors = normalize(data["vectors"])
                            regions = json.loads(str(data["regions"].item()))
                            if len(vectors) != len(regions) or regions[0]["label"] != "full":
                                vectors = None
                    except Exception:
                        vectors = None
                if vectors is None:
                    image = load_image(photo)
                    views, regions = image_regions(image, self.config.region_mode)
                    with self._encoder_lock:
                        encoder = self._get_encoder()
                        vectors = normalize(encoder.encode_images(views))
                    if len(vectors) != len(regions):
                        raise ValueError("Encoder trả về sai số lượng vector cho vùng ảnh.")
                    atomic_npz(cache_path, vectors=vectors, regions=json.dumps(regions))
                chunks.append(vectors)
                records.extend({"image_id": photo.image_id, **region} for region in regions)
                self._progress(processed=number, message=f"{number}/{len(catalog.photos)} · {photo.image_id}")
            current = Catalog(self.config.data_root)
            if current.fingerprint != catalog.fingerprint:
                raise RuntimeError("Dữ liệu bị thay đổi trong lúc tạo index. Chạy lại để cập nhật.")
            metadata = {"signature": self.config.signature, "dataset": catalog.fingerprint,
                        "model_id": self.config.model_id, "revision": self.config.revision,
                        "region_mode": self.config.region_mode, "created_at": time.time()}
            store = VectorStore(np.concatenate(chunks), records, metadata)
            atomic_npz(self.config.index_root / "index.npz", vectors=store.vectors,
                       records=json.dumps(records, ensure_ascii=False), metadata=json.dumps(metadata))
            with self._state_lock:
                self.store = store
                self.error = ""
                self.build.update(state="complete", message=f"Đã tạo index cho {len(catalog.photos)} ảnh.")
        except Exception as exc:
            logger.exception("Image index build failed")
            with self._state_lock:
                self.error = str(exc)
                self.build.update(state="failed", message=str(exc))

    def validate_batches(self, batches):
        allowed = {b["name"] for b in self.catalog.batches}
        if set(batches) - allowed:
            raise ValueError("Batch không tồn tại: " + ", ".join(sorted(set(batches) - allowed)))

    def browse(self, batch="", offset=0, limit=60):
        if batch:
            self.validate_batches([batch])
        photos = [p for p in self.catalog.photos if not batch or p.batch == batch]
        return {"items": [p.public() for p in photos[offset:offset + limit]], "total": len(photos)}

    def _ready_store(self):
        with self._state_lock:
            if not self.index_ready:
                raise IndexNotReady("Chưa có index phù hợp. Tại dsreborn, chạy .\\backend\\run.ps1 -Mode index rồi khởi động lại backend.")
            return self.store, self.catalog

    def _rank(self, store, catalog, vector, top_k, batches, use_regions, exclude_id=None, image_ids=None):
        self.validate_batches(batches)
        score_sets = store.score_matrix(vector)
        full = score_sets[:, store.full_rows]
        if use_regions:
            regional = score_sets[:, store.region_rows]
            clause_scores = .6 * full + .4 * regional.max(axis=2)
            best = regional.mean(axis=0).argmax(axis=1)
            best_rows = store.region_rows[np.arange(len(best)), best]
        else:
            clause_scores, best_rows = full, store.full_rows
        image_scores = .5 * clause_scores.mean(axis=0) + .5 * clause_scores.min(axis=0)
        allowed = np.ones(len(store.image_ids), dtype=bool)
        if exclude_id is not None:
            allowed &= store.id_array != exclude_id
        if batches:
            allowed &= np.asarray([catalog.by_id[key].batch in batches for key in store.image_ids])
        if image_ids is not None:
            allowed &= np.asarray([key in image_ids for key in store.image_ids])
        positions = np.flatnonzero(allowed)
        positions = positions[np.argsort(-image_scores[positions], kind="stable")[:top_k]]
        results = []
        for position in positions:
            photo = catalog.by_id[store.image_ids[position]]
            region = store.records[int(best_rows[position])]
            results.append({**photo.public(), "score": round(float(image_scores[position]), 6),
                            "matched_region": {key: region[key] for key in ("label", "bbox")}})
        return results, int(allowed.sum())

    def search(self, query, top_k=60, batches=None, use_regions=True, image_ids=None, sub_queries=None):
        started = time.perf_counter()
        store, catalog = self._ready_store()
        self.validate_batches(batches or [])
        with self._encoder_lock:
            encoding_started = time.perf_counter()
            encoder = self._get_encoder()
            vectors, truncated = [], False
            for text in sub_queries or [query]:
                encoded, was_truncated = self._encode_cached(encoder, text)
                vectors.append(encoded)
                truncated = truncated or was_truncated
            vector = np.concatenate(vectors, axis=0)
            encoding_ms = (time.perf_counter()-encoding_started)*1000
        rank_started = time.perf_counter()
        results, total = self._rank(store, catalog, vector, top_k, batches or [], use_regions, image_ids=image_ids)
        warnings = ["Mô tả vượt giới hạn token của model; hãy rút gọn để giữ đủ chi tiết."] if truncated else []
        return {"results": results, "query": query, "total": total,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1), "warnings": warnings,
                "sub_queries": sub_queries or [],
                "timing": {"encode_ms": round(encoding_ms, 2),
                           "rank_ms": round((time.perf_counter()-rank_started)*1000, 2)}}

    def similar(self, image_id, top_k=60, batches=None, use_regions=True, image_ids=None):
        started = time.perf_counter()
        if image_id not in self.catalog.by_id:
            raise KeyError(image_id)
        store, catalog = self._ready_store()
        row = next(row for row in store.rows_by_id[image_id] if store.records[row]["label"] == "full")
        results, total = self._rank(store, catalog, store.vectors[row], top_k,
                                    batches or [], use_regions, exclude_id=image_id, image_ids=image_ids)
        return {"results": results, "query": image_id, "total": total,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}

    def close(self):
        self._stop.set()
        self._executor.shutdown(wait=True, cancel_futures=True)
