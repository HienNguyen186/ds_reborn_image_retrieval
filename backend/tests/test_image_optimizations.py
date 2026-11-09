import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.image_retrieval.api import create_app
from src.image_retrieval.config import Config
from src.image_retrieval.service import ImageSearchService, VectorStore, normalize
from test_image_retrieval import ColorEncoder


class SearchOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        root = Path(self.temp)
        for name in ['Batch1/01_10.jpg', 'Batch1/01_20.jpg', 'Batch2/02_10.jpg']:
            path = root/'data'/name
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', (1280, 720), (210, 40, 40)).save(path)
        self.config = Config(data_root=root/'data', index_root=root/'index')

    def store(self, service):
        rng = np.random.default_rng(314)
        records = []
        for photo, count in zip(service.catalog.photos, [1, 3, 5]):
            for region in range(count):
                records.append({'image_id': photo.image_id, 'label': 'full' if region == 0 else f'crop{region}',
                                'bbox': [region, region, 100, 100]})
        store = VectorStore(rng.normal(size=(len(records), 3)), records,
                            {'dataset': service.catalog.fingerprint, 'signature': self.config.signature})
        service.store = store
        return store

    def test_vectorized_ranking_matches_independent_region_and_clause_reference(self):
        service = ImageSearchService(self.config, ColorEncoder)
        self.addCleanup(service.close)
        store = self.store(service)
        queries = normalize([[1, .4, .2], [.1, .6, 1]])
        for regions in [False, True]:
            expected = []
            for key, rows in store.rows_by_id.items():
                per_clause = []
                for query in queries:
                    values = store.vectors[rows] @ query
                    per_clause.append(.6*values[0]+.4*max(values) if regions else values[0])
                expected.append((key, .5*float(np.mean(per_clause))+.5*min(per_clause)))
            expected.sort(key=lambda value: (-value[1], value[0]))
            actual, total = service._rank(store, service.catalog, queries, 3, [], regions)
            self.assertEqual(total, 3)
            self.assertEqual([p['image_id'] for p in actual], [p[0] for p in expected])
            np.testing.assert_allclose([p['score'] for p in actual], [p[1] for p in expected], atol=1e-6)

    def test_repeated_text_reuses_embedding_but_filters_and_limits_still_apply(self):
        class CountingEncoder(ColorEncoder):
            count = 0
            def encode_text(self, text):
                self.count += 1
                return super().encode_text(text)
        service = ImageSearchService(self.config, CountingEncoder)
        self.addCleanup(service.close)
        self.store(service)
        first = service.search('áo đỏ', top_k=3)
        second = service.search('áo đỏ', top_k=1, batches=['Batch2'])
        self.assertEqual(service._encoder.count, 1)
        self.assertEqual(len(first['results']), 3)
        self.assertEqual(len(second['results']), 1)
        self.assertEqual(second['results'][0]['batch'], 'Batch2')

    def test_thumbnail_keeps_original_and_uses_disk_cache(self):
        with TestClient(create_app(self.config, ColorEncoder)) as client:
            url = '/api/image/Batch1/01_10.jpg'
            original = (self.config.data_root/'Batch1/01_10.jpg').read_bytes()
            thumb = client.get(url+'?size=320')
            self.assertEqual(thumb.status_code, 200)
            with Image.open(io.BytesIO(thumb.content)) as image:
                self.assertEqual(image.size, (320, 180))
            with patch('src.image_retrieval.thumbnails.load_image', side_effect=AssertionError('Cache should be used')):
                self.assertEqual(client.get(url+'?size=320').content, thumb.content)
            self.assertEqual(client.get(url).content, original)
            self.assertEqual(client.get(url+'?size=4096').status_code, 422)
