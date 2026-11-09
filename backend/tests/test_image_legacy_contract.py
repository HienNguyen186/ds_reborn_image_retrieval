"""Contract used by the original, unchanged React frontend.

The UI still calls its video-oriented API. These tests ensure the image
adapter preserves original JPEG identity and model provenance at that boundary.
No timestamps or actual video files are assumed for the photo collection.
"""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.image_retrieval.api import create_app
from src.image_retrieval.config import Config
from test_image_retrieval import ColorEncoder


class OriginalFrontendContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="image-legacy-contract-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data_root = self.root / "data"
        self.paths = {
            "Batch1/08_1002.jpg": (240, 0, 0),
            "Batch1/08_1010.jpg": (0, 180, 0),
            "Batch2/11_2625.jpg": (0, 0, 110),
            "Batch2/08_1020.jpg": (120, 0, 0),
        }
        for image_id, color in self.paths.items():
            path = self.data_root / image_id
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (128, 72), color).save(path, quality=100, subsampling=0)
        self.config = Config(data_root=self.data_root, index_root=self.root / "index")

    def client(self):
        return TestClient(create_app(self.config, encoder_factory=ColorEncoder))

    def build(self, client):
        response = client.post("/api/index/build", json={"rebuild": False})
        self.assertIn(response.status_code, (200, 202), response.text)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status = client.get("/api/status").json()
            if status["build"]["state"] in {"complete", "failed"}:
                self.assertEqual(status["build"]["state"], "complete", status)
                return
            time.sleep(0.025)
        self.fail("Index build timed out")

    def search(self, client, **overrides):
        body = {
            "dataset": "aic", "query": "người áo đỏ", "video_ids": [],
            "top_k": 4, "candidate_multiplier": 5, "use_split": True,
            "use_translate": True, "search_mode": "semantic", "model_key": "siglip2",
            "duration_limit": -1, "reasoning": False,
        }
        body.update(overrides)
        return client.post("/api/search", json=body)

    def assert_legacy_item(self, client, item, model_key="siglip2"):
        for field in ("video_id", "frame_id", "frame_name", "image_url", "similarity",
                      "timestamp", "rank", "model_key", "dataset", "collection", "raw"):
            self.assertIn(field, item)
        self.assertTrue(item["video_id"])
        self.assertIsInstance(item["frame_id"], int)
        self.assertIsInstance(item["similarity"], (int, float))
        self.assertEqual(item["model_key"], model_key)
        self.assertGreaterEqual(item["rank"], 1)
        image_id = item.get("image_id") or item["raw"].get("image_id")
        self.assertIn(image_id, self.paths)
        self.assertEqual(item["frame_name"], Path(image_id).name)
        self.assertFalse(item.get("image_rel_path"), "A remote frontend asset base must not override the local image URL")
        response = client.get(item["image_url"])
        self.assertEqual(response.status_code, 200, response.text[:100])
        self.assertEqual(response.content, (self.data_root / image_id).read_bytes())
        self.assertEqual(item["raw"]["keyframe_id"], item["frame_id"])
        self.assertIsNone(item["raw"]["frame_idx"])
        self.assertIsNone(item["timestamp"])

    def test_bootstrap_endpoints_and_string_model_keys(self):
        with self.client() as client:
            health = client.get("/api/health")
            self.assertEqual(health.status_code, 200, health.text)
            config = client.get("/api/config")
            self.assertEqual(config.status_code, 200, config.text)
            config = config.json()
            self.assertIn("search", config)
            for key in ("default_top_k", "max_top_k", "candidate_multiplier", "available_modes",
                        "default_search_mode", "default_duration_limit", "default_model_key"):
                self.assertIn(key, config["search"])
            self.assertEqual(config["search"]["default_model_key"], "siglip2")
            self.assertFalse(config["ocr"]["available"])
            self.assertFalse(config["asr"]["available"])
            self.assertIn("surrounding_radius", config["ui"])
            self.assertIn("max_surrounding_radius", config["ui"])
            self.assertIn("enabled_default", config["translate"])
            self.assertIn(config["datasets"]["default"], ("aic", "cam"))
            self.build(client)
            models = client.get("/api/search/models", params={"dataset": "aic"})
            self.assertEqual(models.status_code, 200, models.text)
            self.assertEqual(models.json()["models"], ["siglip2"])
            self.assertTrue(all(isinstance(key, str) for key in models.json()["models"]))

    def test_old_search_payload_returns_normalizable_original_images(self):
        with self.client() as client:
            self.build(client)
            response = self.search(client)
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            self.assertEqual(data["model_key"], "siglip2")
            self.assertEqual(data["search_mode"], "semantic")
            self.assertEqual(data["count"], len(data["results"]))
            self.assertGreaterEqual(data["latency_ms"], 0)
            self.assertEqual(len(data["results"]), 4)
            identities = []
            for item in data["results"]:
                self.assert_legacy_item(client, item)
                identities.append((item["video_id"], item["frame_id"]))
            self.assertEqual(len(set(identities)), 4)

    def test_video_id_filter_is_honored_and_unknown_model_rejected(self):
        with self.client() as client:
            self.build(client)
            all_items = self.search(client).json()["results"]
            source = all_items[0]
            response = self.search(client, video_ids=[source["video_id"]], top_k=1)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()["results"])
            self.assertTrue(all(item["video_id"] == source["video_id"] for item in response.json()["results"]))
            unknown = self.search(client, video_ids=["not-a-real-group"])
            self.assertIn(unknown.status_code, (200, 422), unknown.text)
            if unknown.status_code == 200:
                self.assertEqual(unknown.json()["results"], [])
            wrong_model = self.search(client, model_key="not-loaded")
            self.assertIn(wrong_model.status_code, (400, 422), wrong_model.text)

    def test_catalog_and_frame_navigation_use_only_existing_photos(self):
        with self.client() as client:
            self.build(client)
            items = self.search(client).json()["results"]
            groups = client.get("/api/video-ids", params={"dataset": "aic"})
            self.assertEqual(groups.status_code, 200, groups.text)
            self.assertEqual(set(groups.json()["video_ids"]), {item["video_id"] for item in items})
            source = items[0]
            params = {"dataset": "aic", "video_id": source["video_id"], "keyframe_id": source["frame_id"]}
            info = client.get("/api/frame-info", params=params)
            self.assertEqual(info.status_code, 200, info.text)
            self.assert_legacy_item(client, info.json())
            self.assertEqual(info.json()["frame_name"], source["frame_name"])
            surrounding = client.get("/api/surrounding-frames", params={**params, "radius": 2})
            self.assertEqual(surrounding.status_code, 200, surrounding.text)
            frames = surrounding.json()["frames"]
            self.assertTrue(frames)
            self.assertLessEqual(len(frames), 5)
            self.assertIn(source["frame_id"], [item["frame_id"] for item in frames])
            for frame in frames:
                self.assertEqual(frame["video_id"], source["video_id"])
                self.assert_legacy_item(client, frame)
            missing = client.get("/api/frame-info", params={**params, "keyframe_id": 999999})
            self.assertEqual(missing.status_code, 404, missing.text)

    def test_similarity_uses_legacy_identity_and_model_provenance(self):
        with self.client() as client:
            self.build(client)
            source = self.search(client).json()["results"][0]
            response = client.post("/api/similarity-search", json={
                "dataset": "aic", "video_id": source["video_id"], "frame_id": source["frame_id"],
                "video_ids": [], "top_k": 3, "model_key": "siglip2",
            })
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            self.assertEqual(data["model_key"], "siglip2")
            self.assertEqual(data["count"], len(data["results"]))
            self.assertGreaterEqual(data["latency_ms"], 0)
            self.assertIn("source", data)
            for item in data["results"]:
                self.assert_legacy_item(client, item)

    def test_unavailable_text_sources_fail_explicitly(self):
        with self.client() as client:
            self.build(client)
            for mode in ("ocr", "asr"):
                response = self.search(client, search_mode=mode)
                self.assertIn(response.status_code, (400, 422, 501, 503), response.text)

    def test_hardcoded_dataset_choices_are_explicit_current_corpus_aliases(self):
        with self.client() as client:
            self.build(client)
            aic = self.search(client, dataset="aic")
            cam = self.search(client, dataset="cam")
            self.assertEqual(aic.status_code, 200, aic.text)
            self.assertEqual(cam.status_code, 200, cam.text)
            aic_items, cam_items = aic.json()["results"], cam.json()["results"]
            self.assertEqual([item["image_id"] for item in aic_items], [item["image_id"] for item in cam_items])
            for item in cam_items:
                self.assertEqual(item["dataset"], "cam")
                self.assertEqual(item["collection"], "cam")
                self.assert_legacy_item(client, item)

    def test_cors_accepts_header_sent_by_unchanged_frontend(self):
        with self.client() as client:
            response = client.options("/api/search", headers={
                "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,ngrok-skip-browser-warning",
            })
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:5173")

    def test_and_clauses_prefer_one_image_matching_both_conditions(self):
        # Red-only and blue-only photos each satisfy just one clause. The
        # mixed-color photo must outrank both when the clauses are combined
        # within each image, rather than by concatenating independent hits.
        mixed_id = "Batch3/12_1500.jpg"
        self.paths[mixed_id] = (200, 0, 200)
        path = self.data_root / mixed_id
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (128, 72), self.paths[mixed_id]).save(path, quality=100, subsampling=0)
        with self.client() as client:
            self.build(client)
            response = self.search(client, query="áo đỏ AND xanh dương", use_split=True, use_regions=False)
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            self.assertEqual(data["results"][0]["image_id"], mixed_id)
            self.assertEqual(len(data["sub_queries"]), 2)
            self.assert_legacy_item(client, data["results"][0])
            unsplit = self.search(client, query="áo đỏ AND xanh dương", use_split=False, use_regions=False)
            self.assertEqual(unsplit.status_code, 200, unsplit.text)
            self.assertNotEqual(unsplit.json()["results"][0]["image_id"], mixed_id)


if __name__ == "__main__":
    unittest.main()
