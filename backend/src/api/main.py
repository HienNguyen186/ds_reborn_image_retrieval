"""ASGI compatibility entrypoint for the current image dataset.

Original video bootstrap is retained in src.api.video_main.
Run from backend: python -m uvicorn src.api.main:app --port 8000
"""
from src.image_retrieval.api import create_app

app = create_app()

__all__ = ["app"]
