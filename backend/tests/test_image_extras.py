"""Image-only features exposed through the original frontend API contracts."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.image_retrieval.api import create_app
from src.image_retrieval.config import Config
from test_image_retrieval import ColorEncoder


class ImageExtrasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="image-extras-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = Config(data_root=self.root / "data", index_root=self.root / "index")
        for image_id, color in {
            "Batch1/08_1002.jpg": (210, 40, 40),
            "Batch1/08_1010.jpg": (35, 90, 200),
            "Batch2/11_2625.jpg": (30, 150, 60),
        }.items():
            path = self.config.data_root / image_id
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (100, 60), color).save(path, quality=100, subsampling=0)

    def client(self):
        return TestClient(create_app(self.config, encoder_factory=ColorEncoder))

    def build(self, client):
        self.assertEqual(client.post("/api/index/build", json={}).status_code, 202)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status = client.get("/api/status").json()
            if status["build"]["state"] != "running":
                self.assertEqual(status["build"]["state"], "complete", status)
                return
            time.sleep(.025)
        self.fail("Build timed out")

    def color_search(self, client, **overrides):
        payload = {"dataset": "aic", "cells": [{"row": 2, "col": 2, "color": "red"}],
                   "top_k": 3, "video_ids": []}
        payload.update(overrides)
        return client.post("/api/search/color", json=payload)

    def image_bytes(self, color=(210, 40, 40)):
        data = io.BytesIO()
        Image.new("RGB", (60, 40), color).save(data, format="JPEG", quality=100, subsampling=0)
        return data.getvalue()

    def multimodal(self, client, payload=None, files=None):
        payload = payload or {"dataset": "aic", "query": "", "clauses": [{"text": "", "image_indices": [0]}],
                              "top_k": 3, "model_key": "siglip2", "search_mode": "semantic"}
        files = files or [("images", ("example.jpg", self.image_bytes(), "image/jpeg"))]
        return client.post("/api/search/multimodal", data={"request_json": json.dumps(payload)}, files=files)

    def test_color_search_works_without_embedding_index_and_preserves_identity(self):
        with self.client() as client:
            self.assertFalse(client.get("/api/status").json()["index_ready"])
            response = self.color_search(client)
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            self.assertEqual(data["search_mode"], "color")
            self.assertEqual(data["results"][0]["image_id"], "Batch1/08_1002.jpg")
            self.assertEqual(data["results"][0]["similarity"], 1)
            self.assertEqual(data["results"][0]["frame_name"], "08_1002.jpg")
            self.assertEqual(client.get(data["results"][0]["image_url"]).status_code, 200)

    def test_color_filter_and_validation(self):
        with self.client() as client:
            response = self.color_search(client, video_ids=["Batch2/11"], top_k=1)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual([item["video_id"] for item in response.json()["results"]], ["Batch2/11"])
            for cells in ([], [{"row": 5, "col": 0, "color": "red"}],
                          [{"row": 0, "col": 0, "color": "unknown"}],
                          [{"row": 0, "col": 0, "color": "red"}] * 2):
                response = self.color_search(client, cells=cells)
                self.assertEqual(response.status_code, 422, response.text)

    def test_color_cache_survives_restart_and_invalidates_for_changed_image(self):
        with self.client() as client:
            self.assertEqual(self.color_search(client).status_code, 200)
        self.assertTrue((self.config.index_root / "color_grid.npz").is_file())
        with self.client() as client, patch("src.image_retrieval.extras.load_image", side_effect=AssertionError("cache ignored")):
            self.assertEqual(self.color_search(client).status_code, 200)
        source = self.config.data_root / "Batch1/08_1002.jpg"
        Image.new("RGB", (110, 70), (35, 90, 200)).save(source, quality=100, subsampling=0)
        with self.client() as client:
            response = self.color_search(client)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["results"][0]["similarity"], 0)

    def test_multimodal_image_vector_is_real_shared_encoder_and_model_isolation_holds(self):
        with self.client() as client:
            self.build(client)
            response = self.multimodal(client)
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            self.assertEqual(data["model_key"], "siglip2")
            self.assertEqual(data["results"][0]["image_id"], "Batch1/08_1002.jpg")
            self.assertTrue(all(item["model_key"] == "siglip2" for item in data["results"]))
            self.assertGreater(data["results"][0]["similarity"], .99)

    def test_multimodal_text_and_image_filter(self):
        with self.client() as client:
            self.build(client)
            payload = {"dataset": "cam", "query": "áo đỏ", "clauses": [{"text": "áo đỏ", "image_indices": [0]}],
                       "top_k": 1, "model_key": "siglip2", "video_ids": ["Batch2/11"]}
            response = self.multimodal(client, payload=payload)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(response.json()["results"]), 1)
            self.assertEqual(response.json()["results"][0]["video_id"], "Batch2/11")
            self.assertEqual(response.json()["results"][0]["dataset"], "cam")

    def test_multimodal_rejects_bad_files_references_and_temporal_request(self):
        with self.client() as client:
            for payload, files, code in [
                ({"clauses": [{"image_indices": [9]}]}, None, 422),
                ({"clauses": [{"image_indices": [0]}]}, [("images", ("bad.jpg", b"not an image", "image/jpeg"))], 422),
                ({"clauses": [{"image_indices": [0]}]}, [("images", ("large.jpg", b"x" * (8 * 1024 * 1024 + 1), "image/jpeg"))], 413),
                ({"query": "THEN cook", "clauses": []}, None, 501),
                ({"clauses": [{"text": "cook", "connector_before": "THEN"}]}, None, 501),
                ({"model_key": "wrong", "clauses": []}, None, 422),
            ]:
                response = self.multimodal(client, payload=payload, files=files)
                self.assertEqual(response.status_code, code, response.text)

    def test_multimodal_requires_embedding_index(self):
        with self.client() as client:
            response = self.multimodal(client)
            self.assertEqual(response.status_code, 503, response.text)


if __name__ == "__main__":
    unittest.main()
