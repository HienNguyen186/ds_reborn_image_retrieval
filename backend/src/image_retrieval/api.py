from __future__ import annotations

from contextlib import asynccontextmanager
import re
import asyncio

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from .config import Config, PROJECT_ROOT, load_config
from .service import ImageSearchService, IndexNotReady
from .legacy import LegacyAdapter, LegacyOptions, check_mode, make_router
from .extras import make_router as make_extras_router
from .dres import make_router as make_dres_router
from .thumbnails import thumbnail_path
from .dres_submission import make_router as make_submission_router


class SearchRequest(LegacyOptions):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=60, ge=1, le=500)
    batches: list[str] = Field(default_factory=list, max_length=100)
    use_regions: bool = True
    search_mode: str = "semantic"
    use_split: bool | None = True
    use_translate: bool | None = False
    candidate_multiplier: int | None = Field(default=None, ge=1, le=100)
    duration_limit: float | None = -1
    reasoning: bool = False

    @field_validator("query")
    @classmethod
    def nonblank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Nhập mô tả ảnh cần tìm.")
        return value


class SimilarRequest(BaseModel):
    image_id: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=60, ge=1, le=500)
    batches: list[str] = Field(default_factory=list, max_length=100)
    use_regions: bool = True


class BuildRequest(BaseModel):
    rebuild: bool = False


def create_app(config: Config | None = None, encoder_factory=None):
    config = config or load_config()

    @asynccontextmanager
    async def lifespan(app):
        app.state.service = ImageSearchService(config, encoder_factory)
        app.state.legacy = LegacyAdapter(app.state.service)
        if config.preload_model and app.state.service.index_ready:
            await asyncio.to_thread(app.state.service.prepare)
        yield
        app.state.service.close()

    app = FastAPI(title="DS Reborn · Image Search", version="1.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "ngrok-skip-browser-warning"])

    @app.get("/api/status")
    def status():
        return app.state.service.status()

    @app.get("/api/images")
    def images(batch: str = "", offset: int = Query(0, ge=0), limit: int = Query(60, ge=1, le=500)):
        try:
            return app.state.service.browse(batch, offset, limit)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/image/{image_id:path}")
    def image(image_id: str, size: int | None = Query(None, ge=160, le=960)):
        # Only IDs discovered inside data_root may be served; never accept a raw path.
        photo = app.state.service.catalog.by_id.get(image_id)
        if photo is None or not photo.path.resolve().is_relative_to(config.data_root) or not photo.path.is_file():
            raise HTTPException(404, "Không tìm thấy ảnh.")
        if size is not None:
            path = thumbnail_path(photo, config.index_root, size)
            return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
        return FileResponse(photo.path)

    @app.post("/api/index/build", status_code=202)
    def build(request: BuildRequest = BuildRequest()):
        return app.state.service.start_build(request.rebuild)

    def run_search(function, **kwargs):
        try:
            return function(**kwargs)
        except HTTPException:
            raise
        except IndexNotReady as exc:
            raise HTTPException(503, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, "Không tìm thấy ảnh.") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(503, f"Không thể chạy model: {exc}") from exc

    @app.post("/api/search")
    def search(request: SearchRequest):
        return run_search(compat_search, payload=request)

    def compat_search(payload):
        request = payload if isinstance(payload, SearchRequest) else SearchRequest.model_validate(payload)
        check_mode(request.search_mode, request.query)
        legacy = app.state.legacy
        clauses = [part.strip() for part in re.split(r"\bAND\b", request.query) if part.strip()] if request.use_split else []
        if len(clauses) > 8:
            raise ValueError("Tối đa 8 mệnh đề AND cho một truy vấn.")
        if request.use_split and not clauses:
            raise ValueError("Cần mô tả ảnh giữa các mệnh đề AND.")
        response = legacy.service.search(request.query, request.top_k, request.batches, request.use_regions,
                                          image_ids=legacy.filter_ids(request.video_ids),
                                          sub_queries=clauses if len(clauses) > 1 else None)
        return legacy.response(response, request.dataset, request.search_mode)

    app.state.compat_search = compat_search

    @app.post("/api/similar")
    def similar(request: SimilarRequest):
        return run_search(app.state.service.similar, **request.model_dump())

    app.include_router(make_router(run_search))
    app.include_router(make_extras_router(run_search))
    app.include_router(make_dres_router())
    app.include_router(make_submission_router())

    # Production: `npm run build`, then serve the same UI on port 8000.
    dist = PROJECT_ROOT / "frontend" / "dist"
    if (dist / "index.html").is_file():
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app
