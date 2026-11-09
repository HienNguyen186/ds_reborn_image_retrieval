"""Default entrypoint for the current Batch*/image.jpg dataset.

Run from backend: python -m uvicorn main:app --host 127.0.0.1 --port 8000
src.api.main:app is an alias for this image server. The previous video
bootstrap remains available as src.api.video_main:app.
"""

from src.image_retrieval.api import create_app

app = create_app()

__all__ = ["app"]
