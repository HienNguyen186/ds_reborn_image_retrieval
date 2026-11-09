"""DRES login for the unchanged frontend; credentials are never persisted."""
from __future__ import annotations

import json
from urllib.parse import urlsplit

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, SecretStr

from .config import PROJECT_ROOT


class DresLoginRequest(BaseModel):
    dres_url: str = ""
    username: str
    password: SecretStr


def load_dres_config():
    path = PROJECT_ROOT / "backend/configs/dres.json"
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_dres_url(value: str, configured: str):
    parts = urlsplit((value or configured).strip())
    allowed = urlsplit(configured)
    if (parts.scheme != "https" or parts.netloc.lower() != allowed.netloc.lower()
            or parts.username or parts.password):
        raise HTTPException(400, f"DRES URL phải thuộc {configured}. Có thể nhập URL trang evaluation hoặc URL gốc.")
    return f"{parts.scheme}://{parts.netloc}".rstrip("/")


def make_router():
    router = APIRouter(tags=["dres-login"])

    @router.post("/api/dres/login")
    def login(payload: DresLoginRequest):
        configured = load_dres_config()["base_url"]
        base = normalize_dres_url(payload.dres_url, configured)
        if not payload.username.strip() or not payload.password.get_secret_value():
            raise HTTPException(400, "Cần tài khoản và mật khẩu DRES.")
        try:
            with requests.Session() as session:
                response = session.post(base + "/api/v2/login",
                                        json={"username": payload.username.strip(),
                                              "password": payload.password.get_secret_value()},
                                        timeout=15, allow_redirects=False)
                if response.status_code in {401, 403}:
                    raise HTTPException(response.status_code, "Tài khoản hoặc mật khẩu DRES không đúng, hoặc tài khoản không có quyền đăng nhập.")
                if not 200 <= response.status_code < 300:
                    raise HTTPException(502, f"DRES trả HTTP {response.status_code} khi đăng nhập.")
                try:
                    data = response.json()
                except ValueError:
                    raise HTTPException(502, "DRES không trả dữ liệu đăng nhập JSON hợp lệ.") from None
                if not isinstance(data, dict):
                    raise HTTPException(502, "Phản hồi đăng nhập DRES không hợp lệ.")
                session_id = str(data.get("sessionId") or data.get("session_id") or "").strip()
                if not session_id:
                    fallback = session.get(base + "/api/v2/user/session", timeout=15, allow_redirects=False)
                    if fallback.status_code == 200:
                        session_id = fallback.text.strip().strip('"')
                if not session_id:
                    raise HTTPException(502, "DRES đăng nhập nhưng không trả session ID.")
                evaluations, warnings = [], []
                try:
                    result = session.get(base + "/api/v2/client/evaluation/list", params={"session": session_id},
                                         timeout=10, allow_redirects=False)
                    if result.status_code == 200:
                        values = result.json()
                        if isinstance(values, list):
                            evaluations = [item for item in values if isinstance(item, dict)]
                    else:
                        warnings.append("Đã đăng nhập; chưa tải được danh sách evaluation.")
                except (requests.RequestException, ValueError):
                    warnings.append("Đã đăng nhập; chưa tải được danh sách evaluation.")
        except requests.RequestException:
            # Exception URLs can contain the session token: never echo them.
            raise HTTPException(502, "Không kết nối được DRES. Kiểm tra mạng và địa chỉ máy chủ.") from None
        active = next((item for item in evaluations if str(item.get("status", "")).upper() == "ACTIVE"), None)
        return {"status": "ok", "session_id": session_id,
                "evaluation_id": active.get("id") if active else None,
                "evaluations": evaluations, "warnings": warnings,
                "user": {key: data[key] for key in ("id", "username", "role") if key in data}}

    return router
