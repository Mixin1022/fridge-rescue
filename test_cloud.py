import http.client
import json
import tempfile
import threading
import io
from email.message import Message
from unittest.mock import Mock, patch
import unittest
from pathlib import Path

from cloud_store import Store
from cloud_server import make_server
from build_library import app_html


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent / 'work')
        self.store = Store(self.temp.name)
        self.recipe = {'steps': [{'instruction': '切好番茄'}], 'input_video': 'private-local-path', 'api_key': 'should-not-be-stored'}

    def tearDown(self):
        self.temp.cleanup()

    def test_recipe_dedup_metadata_and_private_fields(self):
        first = self.store.save_recipe({'recipe': self.recipe, 'title': '我的冷汤', 'cuisine': '西班牙菜'})
        second = self.store.save_recipe({'recipe': self.recipe})
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(len(self.store.recipes()), 1)
        self.assertEqual(second['title'], '我的冷汤')
        self.assertNotIn('api_key', second['recipe'])
        self.assertNotIn('input_video', second['recipe'])

    def test_restart_recovers_interrupted_job(self):
        identifier = self.store.create_job('link', 'https://xhslink.cn/o/test')
        self.assertEqual(self.store.claim()[0], identifier)
        restarted = Store(self.temp.name)
        self.assertEqual(restarted.claim()[0], identifier)

    def test_queue_limit(self):
        for _ in range(10):
            self.store.create_job('link', 'https://xhslink.cn/o/test')
        with self.assertRaises(ValueError):
            self.store.create_job('link', 'https://xhslink.cn/o/test')

    def test_malformed_analysis_rejected(self):
        with self.assertRaises(ValueError):
            self.store.save_recipe({'recipe': {'steps': [], 'deepseek': ['bad']}})


class HandlerTests(StoreTests):
    def setUp(self):
        super().setUp()
        self.token = 'test-access-token-not-a-real-secret'
        self.server = make_server(('127.0.0.1', 0), self.store, self.token)

    def tearDown(self):
        self.server.server_close()
        super().tearDown()

    def request(self, method, path, body=None, authenticated=True):
        headers = Message()
        headers['Content-Type'] = 'application/json'
        if authenticated:
            headers['X-Fridge-Token'] = self.token
        raw = json.dumps(body).encode('utf-8') if body is not None else b''
        headers['Content-Length'] = str(len(raw))
        handler = self.server.RequestHandlerClass.__new__(self.server.RequestHandlerClass)
        handler.headers = headers
        handler.path = path
        handler.request_version = 'HTTP/1.1'
        handler.command = method
        handler.requestline = method + ' ' + path + ' HTTP/1.1'
        handler.rfile = io.BytesIO(raw)
        handler.wfile = io.BytesIO()
        handler.connection = Mock()
        getattr(handler, 'do_' + method)()
        response = handler.wfile.getvalue()
        head, content = response.split(b'\r\n\r\n', 1)
        return int(head.split()[1]), json.loads(content)

    def test_private_library_requires_token(self):
        self.assertEqual(self.request('GET', '/api/recipes', authenticated=False)[0], 401)

    def test_import_and_edit_roundtrip(self):
        code, entry = self.request('POST', '/api/recipes', {'recipe': self.recipe})
        self.assertEqual(code, 201)
        self.assertEqual(self.request('PATCH', '/api/recipes/' + entry['id'], {'title': '手机菜谱', 'reviewed': True})[0], 200)
        self.assertEqual(self.request('GET', '/api/recipes')[1][0]['title'], '手机菜谱')

    def test_arbitrary_url_not_queued(self):
        self.assertEqual(self.request('POST', '/api/jobs/link', {'share': 'https://127.0.0.1/private'})[0], 400)
        self.assertEqual(self.store.jobs(), [])

    def test_share_queues_then_job_is_visible(self):
        self.assertEqual(self.request('POST', '/api/jobs/link', {'share': '分享 https://xhslink.cn/o/test'})[0], 202)
        self.assertEqual(self.request('GET', '/api/jobs')[1][0]['state'], 'queued')

    def test_invalid_video_rejected(self):
        self.assertEqual(self.request('POST', '/api/jobs/video', {'not': 'video'})[0], 400)


class ShellTests(unittest.TestCase):
    def test_cloud_page_contains_no_private_seed(self):
        html = app_html([], cloud=True)
        self.assertIn('const CLOUD_MODE=true', html)
        self.assertIn('X-Fridge-Token', html)
        self.assertNotIn('__CLOUD_CLIENT__', html)
        self.assertNotIn('__PWA_HEAD__', html)
        self.assertNotIn('sk-', html)

    def test_offline_page_does_not_connect_to_api(self):
        html = app_html([], cloud=False)
        self.assertIn('const CLOUD_MODE=false', html)
        self.assertNotIn('X-Fridge-Token', html)


class WorkerTests(unittest.TestCase):
    def test_video_to_persisted_recipe(self):
        from make_test_video import generate
        from cloud_worker import process_job
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent / 'work') as folder:
            store = Store(folder)
            video = generate(Path(folder) / 'test.mp4')
            identifier = store.create_job('video', str(video))
            evidence = [{'start': 0, 'end': 1, 'source': 'ocr', 'text': '番茄切成小块'}]
            model = {'title':'番茄','ingredients':[{'text':'番茄','evidence_ids':[0]}],'steps':[{'text':'切成小块','evidence_ids':[0]}],'uncertainties':[]}
            with patch('video_recipe.ocr_video', return_value=evidence), patch('video_recipe.transcribe', return_value=[]), patch('deepseek_recipe.load_config', return_value=('test-key', 'test-model')), patch('deepseek_recipe.analyze', return_value=model), patch('recipe_review_cycle.review', return_value={'passed':True,'issues':[]}):
                process_job(store, store.claim())
            self.assertEqual(store.jobs()[0]['state'], 'completed')
            self.assertEqual(len(store.recipes()), 1)
            output = Path(folder) / 'jobs' / identifier
            self.assertTrue((output / 'recipe.html').is_file())
            result = json.loads((output / 'recipe.json').read_text(encoding='utf-8'))
            self.assertEqual(result['analysis_status'], 'deepseek')
            self.assertTrue(result['auto_review']['passed'])
