import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.image_retrieval.api import create_app
from src.image_retrieval.config import Config


def response(code=200, data=None, text=""):
    return Mock(status_code=code, json=Mock(return_value=data), text=text)


class DresLoginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.client = self.enterContext(TestClient(create_app(Config(data_root=root/'data', index_root=root/'index'))))
        self.factory = self.enterContext(patch('src.image_retrieval.dres.requests.Session'))
        self.remote = self.factory.return_value.__enter__.return_value
        self.payload = {'dres_url': 'https://dres.2hbread.com/evaluation/list',
                        'username': 'test-user', 'password': 'test-password'}

    def test_login_normalizes_page_url_and_returns_frontend_contract(self):
        self.remote.post.return_value = response(data={'sessionId': 'test-session', 'username': 'test-user', 'password': 'must-not-return'})
        self.remote.get.return_value = response(data=[{'id': 'old', 'status': 'FINISHED'}, {'id': 'current', 'status': 'ACTIVE'}])
        result = self.client.post('/api/dres/login', json=self.payload)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['session_id'], 'test-session')
        self.assertEqual(result.json()['evaluation_id'], 'current')
        self.assertNotIn('password', result.json()['user'])
        self.assertNotIn('must-not-return', result.text)
        self.assertEqual(self.remote.post.call_args.args[0], 'https://dres.2hbread.com/api/v2/login')
        self.assertFalse(self.remote.post.call_args.kwargs['allow_redirects'])

    def test_rejects_credentials_to_an_unconfigured_host(self):
        for url in ['https://another.example', 'http://dres.2hbread.com', 'https://dres.2hbread.com@another.example']:
            result = self.client.post('/api/dres/login', json={**self.payload, 'dres_url': url})
            self.assertEqual(result.status_code, 400)
        self.remote.post.assert_not_called()

    def test_invalid_password_and_connection_failures_are_safe(self):
        self.remote.post.return_value = response(401, {'description': 'invalid test-password'})
        result = self.client.post('/api/dres/login', json=self.payload)
        self.assertEqual(result.status_code, 401)
        self.assertNotIn('test-password', result.text)
        self.remote.post.side_effect = requests.ConnectionError('secret-session-token')
        result = self.client.post('/api/dres/login', json=self.payload)
        self.assertEqual(result.status_code, 502)
        self.assertNotIn('secret-session-token', result.text)

    def test_session_fallback_and_evaluation_failure_preserve_login(self):
        self.remote.post.return_value = response(data={'username': 'test-user'})
        self.remote.get.side_effect = [response(text='"fallback-session"'), requests.Timeout('secret')]
        result = self.client.post('/api/dres/login', json=self.payload)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['session_id'], 'fallback-session')
        self.assertTrue(result.json()['warnings'])
        self.assertIsNone(result.json()['evaluation_id'])

    def test_finished_evaluations_are_not_selected_as_active(self):
        self.remote.post.return_value = response(data={'sessionId': 'test-session'})
        self.remote.get.return_value = response(data=[{'id': 'old', 'status': 'FINISHED'}])
        result = self.client.post('/api/dres/login', json=self.payload)
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.json()['evaluation_id'])


if __name__ == '__main__':
    unittest.main()
