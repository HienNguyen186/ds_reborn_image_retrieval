"""Build image-only DRES answers using participant or admin metadata access."""
import hashlib
import json
import threading
import time
from collections import OrderedDict
from urllib.parse import quote, urlsplit

import requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr

from .dres import load_dres_config, normalize_dres_url


class ImageAnswer(BaseModel):
    image_id: str | None = Field(default=None, max_length=1000)
    video_id: str | None = Field(default=None, max_length=1000)
    frame_id: int | None = None


class SubmissionRequest(BaseModel):
    dres_url: str = ""
    session_id: SecretStr
    evaluation_id: str | None = Field(default=None, max_length=256)
    task: str = "kis"
    items: list[ImageAnswer] = Field(min_length=1, max_length=1)
    request_id: str | None = Field(default=None, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")


def configured_media_name(path, config):
    """Map a local filename to DRES imageID (Castle5000 guide, section 2)."""
    naming = config.get("media_name_format", "stem")
    if naming not in {"stem", "filename"}:
        raise HTTPException(500, "media_name_format phải là stem hoặc filename.")
    prefix = config.get("media_name_prefix", "")
    if not isinstance(prefix, str):
        raise HTTPException(500, "media_name_prefix phải là chuỗi ký tự.")
    name = path.stem if naming == "stem" else path.name
    return name if name.startswith(prefix) else prefix + name


def read_json(session, base, path, token):
    try:
        response = session.get(base + path, params={"session": token}, timeout=12, allow_redirects=False)
    except requests.RequestException:
        raise HTTPException(502, "Không đọc được metadata DRES. Chưa gửi đáp án.") from None
    if response.status_code in {401, 403}:
        raise HTTPException(response.status_code, "Session DRES đã hết hạn hoặc không có quyền. Đăng nhập lại.")
    if response.status_code != 200:
        raise HTTPException(502, f"DRES không trả metadata cần thiết (HTTP {response.status_code}). Chưa gửi đáp án.")
    try:
        return response.json()
    except ValueError:
        raise HTTPException(502, "Metadata DRES không phải JSON hợp lệ.") from None


def resolve_submission(service, legacy, payload, session):
    config = load_dres_config()
    base = normalize_dres_url(payload.dres_url, config["base_url"])
    token = payload.session_id.get_secret_value().strip()
    if not token:
        raise HTTPException(401, "Cần đăng nhập DRES trước khi nộp ảnh.")
    # Client endpoints accept ?session=, but collection/media metadata uses
    # CookieAuth in this deployment's OpenAPI. Scope it to the allowed host.
    session.cookies.set("SESSIONID", token, domain=urlsplit(base).hostname, path="/", secure=True)
    if payload.task.lower() != "kis":
        raise HTTPException(422, "Luồng này nộp một ảnh KIS; không chuyển ảnh thành đáp án video hoặc QA.")
    item = payload.items[0]
    if item.image_id:
        photo = service.catalog.by_id.get(item.image_id)
        if photo is None:
            raise HTTPException(404, "Ảnh không thuộc bộ dữ liệu hiện tại.")
        if item.video_id is not None and item.frame_id is not None:
            try:
                if legacy.find(item.video_id, item.frame_id).image_id != photo.image_id:
                    raise HTTPException(422, "image_id và định danh ảnh cũ không khớp.")
            except KeyError:
                raise HTTPException(422, "Định danh nhóm ảnh không hợp lệ.") from None
    else:
        try:
            photo = legacy.find(item.video_id, item.frame_id)
        except (KeyError, ValueError):
            raise HTTPException(404, "Không tìm thấy ảnh để nộp.") from None

    evaluations = read_json(session, base, "/api/v2/client/evaluation/list", token)
    if not isinstance(evaluations, list):
        raise HTTPException(502, "Danh sách evaluation DRES không hợp lệ.")
    active = [ev for ev in evaluations if isinstance(ev, dict) and ev.get("status") == "ACTIVE"]
    if payload.evaluation_id:
        active = [ev for ev in active if ev.get("id") == payload.evaluation_id]
    if len(active) != 1:
        raise HTTPException(409, "Cần chọn đúng một evaluation đang ACTIVE trong Settings.")
    evaluation = active[0]
    current = read_json(session, base, "/api/v2/client/evaluation/currentTask/" + quote(evaluation["id"], safe=""), token)
    if not isinstance(current, dict) or not current.get("name"):
        raise HTTPException(409, "DRES chưa có task đang hoạt động để nộp.")
    if config.get("metadata_mode", "participant") == "participant":
        # Castle5000 imports metadata imageID, not the scanner's bare stem.
        # Its guide requires day1_Kitchen_<stem> and collection castle5000.
        media_name = configured_media_name(photo.path, config)
        duplicates = sum(configured_media_name(item.path, config) == media_name
                         for item in service.catalog.photos)
        if duplicates != 1:
            raise HTTPException(409, "Tên ảnh bị trùng trong dữ liệu local; cần ánh xạ collection rõ ràng trước khi nộp.")
        answer = {"mediaItemName": media_name}
        if config.get("collection_name"):
            answer["mediaItemCollectionName"] = config["collection_name"]
        return {"base": base, "evaluation_id": evaluation["id"], "evaluation_name": evaluation.get("name"),
                "task_name": current["name"], "image_id": photo.image_id, "filename": photo.path.name,
                "media_item_name": media_name, "collection_name": config.get("collection_name"),
                "resolution": "configured_name", "payload": {"answerSets": [{"answers": [answer]}]},
                "warnings": ["Xem trước chưa xác minh ảnh trong danh mục của máy chủ. DRES sẽ kiểm tra tên ảnh khi nhận đáp án."]}
    if config.get("metadata_mode") != "admin":
        raise HTTPException(500, "metadata_mode phải là participant hoặc admin.")
    collections = read_json(session, base, "/api/v2/collection/list", token)
    if not isinstance(collections, list):
        raise HTTPException(502, "Danh sách collection DRES không hợp lệ.")
    configured = config.get("collection_name")
    if configured:
        collections = [collection for collection in collections if isinstance(collection, dict) and collection.get("name") == configured]
    matches = []
    for collection in collections:
        if not isinstance(collection, dict) or not collection.get("id") or not collection.get("name"):
            continue
        values = read_json(session, base, "/api/v2/collection/" + quote(collection["id"], safe="") + "/" + quote(photo.path.stem, safe=""), token)
        if not isinstance(values, list):
            raise HTTPException(502, "Danh sách ảnh DRES không hợp lệ.")
        for remote in values:
            if isinstance(remote, dict) and remote.get("type") == "IMAGE" and remote.get("name") in {photo.path.name, photo.path.stem}:
                matches.append((collection, remote))
    if len(matches) != 1:
        raise HTTPException(409, f"Cần đúng một ảnh DRES khớp {photo.path.name}; tìm thấy {len(matches)}. Kiểm tra collection_name trong configs/dres.json.")
    collection, remote = matches[0]
    answer = {"mediaItemName": remote["name"], "mediaItemCollectionName": collection["name"]}
    body = {"answerSets": [{"taskName": current["name"], "answers": [answer]}]}
    return {"base": base, "evaluation_id": evaluation["id"], "evaluation_name": evaluation.get("name"),
            "task_name": current["name"], "image_id": photo.image_id, "filename": photo.path.name,
            "media_item_name": remote["name"], "collection_name": collection["name"], "resolution": "metadata", "payload": body}


def normalize_verdict(response, token):
    try:
        data = response.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    description = str(data.get("description") or "").replace(token, "[redacted]")[:1000]
    verdict = str(data.get("submission") or "").upper()
    if response.status_code == 412:
        status = "rejected"
        description = description or "DRES từ chối submission (ví dụ đáp án trùng hoặc giới hạn nộp)."
    elif response.status_code == 202:
        status = "pending"
    elif response.status_code == 200 and data.get("status") is not False:
        status = {"CORRECT": "correct", "WRONG": "wrong", "INDETERMINATE": "pending", "UNDECIDABLE": "pending"}.get(verdict, "error")
    else:
        status = "error"
    return {"status": status, "verdict": verdict, "message": description or f"DRES HTTP {response.status_code}",
            "http_status": response.status_code}


def make_router():
    router = APIRouter(tags=["dres-image-submission"])
    lock = threading.Lock()
    completed = OrderedDict()

    @router.post("/api/dres/submit/preview")
    def preview(request: Request, payload: SubmissionRequest):
        with requests.Session() as session:
            resolved = resolve_submission(request.app.state.service, request.app.state.legacy, payload, session)
        return {**{key: value for key, value in resolved.items() if key != "base"}, "dry_run": True}

    @router.post("/api/dres/submit")
    def submit(request: Request, payload: SubmissionRequest):
        token = payload.session_id.get_secret_value().strip()
        fingerprint = hashlib.sha256(payload.model_dump_json(exclude={"session_id", "request_id"}).encode()).hexdigest()
        key = hashlib.sha256((token + ":" + payload.request_id).encode()).hexdigest() if payload.request_id else None
        with lock:
            now = time.monotonic()
            for old in list(completed):
                if now-completed[old][0] > 300:
                    del completed[old]
            if key in completed:
                _, previous, result = completed[key]
                if previous != fingerprint:
                    raise HTTPException(409, "request_id đã được dùng cho một đáp án khác.")
                return {**result, "replayed": True}
            with requests.Session() as session:
                resolved = resolve_submission(request.app.state.service, request.app.state.legacy, payload, session)
                try:
                    response = session.post(resolved["base"] + "/api/v2/submit/" + quote(resolved["evaluation_id"], safe=""),
                                            params={"session": token}, json=resolved["payload"], timeout=15, allow_redirects=False)
                    result = {**normalize_verdict(response, token), "image_id": resolved["image_id"],
                              "media_item_name": resolved["media_item_name"], "evaluation_id": resolved["evaluation_id"],
                              "task_name": resolved["task_name"]}
                except requests.RequestException:
                    # The POST may already have reached DRES. Do not retry it.
                    result = {"status": "unknown", "message": "Không nhận được kết quả nộp. Kiểm tra lịch sử DRES trước khi nộp lại; backend không tự gửi lại.",
                              "image_id": resolved["image_id"], "evaluation_id": resolved["evaluation_id"]}
            if key:
                completed[key] = (now, fingerprint, result)
                while len(completed) > 256:
                    completed.popitem(last=False)
            return result

    return router
