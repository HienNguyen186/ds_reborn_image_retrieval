"""Offline contract tests for the still-image retrieval application.

Run from ``backend`` with::

    ..\env\Scripts\python.exe -m unittest discover -s tests -p test_image_retrieval.py -v

The encoder below deliberately returns vectors with different magnitudes.
It makes cosine normalization, regional result aggregation and correct
image identity testable without downloading any model or contacting a service.
"""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.image_retrieval.api import create_app
from src.image_retrieval.config import Config


class ColorEncoder:
    """Deterministic stand-in for a paired image/text embedding model."""

    device = "cpu"

    def __init__(self, config: Config):
        self.config = config

    def encode_images(self, images: list[Image.Image]) -> np.ndarray:
        return np.asarray(
            [np.asarray(image.convert("RGB"), dtype=np.float32).mean(axis=(0, 1)) for image in images],
            dtype=np.float32,
        )

    def encode_text(self, text: str) -> np.ndarray:
        if "đỏ" in text or "red" in text:
            return np.asarray([70.0, 0.0, 0.0], dtype=np.float32)
        if "blue" in text or "xanh dương" in text:
            return np.asarray([0.0, 0.0, 2.0], dtype=np.float32)
        return np.asarray([1.0, 1.0, 1.0], dtype=np.float32)


class ImageRetrievalAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="image-retrieval-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data_root = self.root / "data"
        self.index_root = self.root / "index"
        self.images = {
            "Batch1/red.jpg": (240, 0, 0),
            "Batch1/green.jpg": (0, 180, 0),
            "Batch2/blue.jpg": (0, 0, 110),
            "Batch2/red.jpg": (120, 0, 0),
            "Batch2/nested/yellow.jpg": (220, 220, 0),
        }
        for image_id, color in self.images.items():
            self.write_image(image_id, color)
        self.config = Config(data_root=self.data_root, index_root=self.index_root)

    def write_image(self, image_id: str, color: tuple[int, int, int]):
        path = self.data_root / image_id
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (128, 72), color).save(path, quality=100, subsampling=0)
        return path

    def client(self, config: Config | None = None):
        return TestClient(create_app(config or self.config, encoder_factory=ColorEncoder))

    def build(self, client: TestClient, rebuild: bool = False):
        response = client.post("/api/index/build", json={"rebuild": rebuild})
        self.assertIn(response.status_code, (200, 202), response.text)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            response = client.get("/api/status")
            self.assertEqual(response.status_code, 200, response.text)
            status = response.json()
            if status["build"]["state"] in {"complete", "failed"}:
                return status
            time.sleep(0.025)
        self.fail("Index build did not leave the running state within 15 seconds")

    def require_index(self, client: TestClient):
        status = self.build(client)
        self.assertEqual(status["build"]["state"], "complete", status)
        self.assertTrue(status["index_ready"], status)
        self.assertEqual(status["indexed_images"], len(self.images))
        return status

    def test_catalog_recurses_and_preserves_batch_relative_identity(self):
        with self.client() as client:
            status = client.get("/api/status").json()
            self.assertEqual(status["image_count"], 5)
            self.assertFalse(status["index_ready"])
            self.assertEqual(
                {item["name"]: item["count"] for item in status["batches"]},
                {"Batch1": 2, "Batch2": 3},
            )
            page = client.get("/api/images", params={"batch": "Batch2", "offset": 0, "limit": 2}).json()
            self.assertEqual(page["total"], 3)
            self.assertEqual(len(page["items"]), 2)
            tail = client.get("/api/images", params={"batch": "Batch2", "offset": 2, "limit": 2}).json()
            items = page["items"] + tail["items"]
            self.assertEqual({item["image_id"] for item in items}, {key for key in self.images if key.startswith("Batch2/")})
            self.assertEqual(len({item["image_id"] for item in items}), 3)
            for item in items:
                self.assertEqual((item["width"], item["height"]), (128, 72))
                self.assertEqual(item["filename"], Path(item["image_id"]).name)
                self.assertEqual(client.get(item["image_url"]).status_code, 200)

    def test_search_requires_index_and_validates_request(self):
        with self.client() as client:
            response = client.post("/api/search", json={"query": "người áo đỏ"})
            self.assertEqual(response.status_code, 503, response.text)
            for body in ({"query": ""}, {"query": "   "}, {"query": "áo đỏ", "top_k": 0}):
                response = client.post("/api/search", json=body)
                self.assertIn(response.status_code, (400, 422), response.text)

    def test_semantic_search_normalizes_and_aggregates_regions(self):
        with self.client() as client:
            self.require_index(client)
            response = client.post("/api/search", json={"query": "người áo đỏ", "top_k": 5, "use_regions": True})
            self.assertEqual(response.status_code, 200, response.text)
            results = response.json()["results"]
            self.assertEqual(len(results), 5)
            self.assertEqual(len({item["image_id"] for item in results}), 5)
            self.assertEqual({item["image_id"] for item in results[:2]}, {"Batch1/red.jpg", "Batch2/red.jpg"})
            scores = [item["score"] for item in results]
            self.assertEqual(scores, sorted(scores, reverse=True))
            self.assertTrue(all(-1.00001 <= score <= 1.00001 for score in scores), scores)
            self.assertAlmostEqual(scores[0], 1.0, places=3)
            self.assertGreaterEqual(response.json()["elapsed_ms"], 0)

    def test_batch_filter_applies_before_topk_and_global_search_works(self):
        with self.client() as client:
            self.require_index(client)
            response = client.post("/api/search", json={"query": "áo đỏ", "top_k": 2, "batches": ["Batch2"], "use_regions": False})
            self.assertEqual(response.status_code, 200, response.text)
            results = response.json()["results"]
            self.assertEqual(len(results), 2)
            self.assertTrue(all(item["batch"] == "Batch2" for item in results))
            self.assertEqual(results[0]["image_id"], "Batch2/red.jpg")
            unknown = client.post("/api/search", json={"query": "áo đỏ", "batches": ["Missing"]})
            self.assertIn(unknown.status_code, (200, 400, 422), unknown.text)
            if unknown.status_code == 200:
                self.assertEqual(unknown.json()["results"], [])

    def test_similarity_finds_related_image_and_handles_missing_identity(self):
        with self.client() as client:
            self.require_index(client)
            response = client.post("/api/similar", json={"image_id": "Batch1/red.jpg", "top_k": 3, "use_regions": True})
            self.assertEqual(response.status_code, 200, response.text)
            results = response.json()["results"]
            self.assertIn("Batch2/red.jpg", [item["image_id"] for item in results[:2]])
            self.assertEqual(len({item["image_id"] for item in results}), len(results))
            missing = client.post("/api/similar", json={"image_id": "Batch1/not-here.jpg"})
            self.assertEqual(missing.status_code, 404, missing.text)

    def test_serves_original_bytes_and_rejects_path_traversal(self):
        outside = self.root / "private.jpg"
        Image.new("RGB", (16, 16), (255, 0, 255)).save(outside)
        with self.client() as client:
            response = client.get("/api/image/Batch1/red.jpg")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, (self.data_root / "Batch1/red.jpg").read_bytes())
            self.assertIn("image/jpeg", response.headers["content-type"])
            for path in ("%2e%2e%2fprivate.jpg", "Batch1%2f..%2f..%2fprivate.jpg", "C%3A%5CWindows%5Cwin.ini"):
                blocked = client.get(f"/api/image/{path}")
                self.assertIn(blocked.status_code, (400, 403, 404), blocked.text[:100])

    def test_saved_index_reopens_without_reencoding(self):
        with self.client() as client:
            self.require_index(client)

        class NeverLoadEncoder:
            def __init__(self, _config):
                raise AssertionError("Loading metadata/index must not load the embedding model")

        with TestClient(create_app(self.config, encoder_factory=NeverLoadEncoder)) as client:
            status = client.get("/api/status").json()
            self.assertTrue(status["index_ready"], status)
            self.assertEqual(status["indexed_images"], 5)
            self.assertEqual(client.get("/api/images").json()["total"], 5)

    def test_modified_dataset_invalidates_persisted_index(self):
        with self.client() as client:
            self.require_index(client)
        self.write_image("Batch1/new.jpg", (100, 120, 170))
        with self.client() as client:
            status = client.get("/api/status").json()
            self.assertEqual(status["image_count"], 6)
            self.assertFalse(status["index_ready"], status)
            response = client.post("/api/search", json={"query": "áo đỏ"})
            self.assertEqual(response.status_code, 503, response.text)

    def test_changed_checkpoint_invalidates_persisted_index(self):
        with self.client() as client:
            self.require_index(client)
        other = Config(data_root=self.data_root, index_root=self.index_root, model_id="different/checkpoint")
        with self.client(other) as client:
            status = client.get("/api/status").json()
            self.assertFalse(status["index_ready"], status)

    def test_editing_existing_image_invalidates_persisted_index(self):
        with self.client() as client:
            self.require_index(client)
        self.write_image("Batch1/red.jpg", (30, 60, 90))
        with self.client() as client:
            status = client.get("/api/status").json()
            self.assertEqual(status["image_count"], 5)
            self.assertFalse(status["index_ready"], status)

    def test_changed_region_configuration_invalidates_persisted_index(self):
        with self.client() as client:
            self.require_index(client)
        other = Config(data_root=self.data_root, index_root=self.index_root, region_mode="none")
        with self.client(other) as client:
            status = client.get("/api/status").json()
            self.assertFalse(status["index_ready"], status)

    def test_corrupt_image_is_reported_and_cannot_silently_claim_full_index(self):
        (self.data_root / "Batch1/broken.jpg").write_bytes(b"this is not a JPEG")
        with self.client() as client:
            status = self.build(client)
            diagnostic = " ".join(str(status.get(key, "")) for key in ("error", "errors", "warnings"))
            diagnostic += " " + str(status["build"].get("message", ""))
            self.assertTrue(status["build"]["state"] == "failed" or "broken.jpg" in diagnostic, status)
            self.assertLessEqual(status["indexed_images"], 5)

    def test_cache_resumes_and_reencodes_only_changed_images(self):
        class CountingEncoder(ColorEncoder):
            image_count = 0

            def encode_images(self, images):
                type(self).image_count += len(images)
                return super().encode_images(images)

        with TestClient(create_app(self.config, encoder_factory=CountingEncoder)) as client:
            self.require_index(client)
            first_count = CountingEncoder.image_count
            self.assertGreater(first_count, 0)
            self.require_index(client)
            self.assertEqual(CountingEncoder.image_count, first_count)
            self.write_image("Batch1/new.jpg", (80, 60, 30))
            status = self.build(client)
            self.assertEqual(status["build"]["state"], "complete", status)
            self.assertEqual(status["indexed_images"], 6)
            increment = CountingEncoder.image_count - first_count
            self.assertGreater(increment, 0)
            self.assertLess(increment, first_count)
            before_rebuild = CountingEncoder.image_count
            status = self.build(client, rebuild=True)
            self.assertEqual(status["build"]["state"], "complete", status)
            self.assertGreater(CountingEncoder.image_count - before_rebuild, increment)

    def test_failed_rebuild_preserves_previous_usable_index(self):
        class ToggleEncoder(ColorEncoder):
            fail_images = False

            def encode_images(self, images):
                if type(self).fail_images:
                    raise RuntimeError("Deliberate encoder failure")
                return super().encode_images(images)

        with TestClient(create_app(self.config, encoder_factory=ToggleEncoder)) as client:
            self.require_index(client)
            saved = (self.index_root / "index.npz").read_bytes()
            ToggleEncoder.fail_images = True
            status = self.build(client, rebuild=True)
            self.assertEqual(status["build"]["state"], "failed", status)
            self.assertTrue(status["index_ready"], status)
            self.assertEqual((self.index_root / "index.npz").read_bytes(), saved)
            response = client.post("/api/search", json={"query": "áo đỏ", "top_k": 2})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(response.json()["results"]), 2)
        with self.client() as client:
            self.assertTrue(client.get("/api/status").json()["index_ready"])


if __name__ == "__main__":
    unittest.main()
