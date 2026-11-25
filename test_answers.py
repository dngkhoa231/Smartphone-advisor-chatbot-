from test_client_helpers import browser_client, authenticated_session
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
import tempfile
from unittest.mock import patch
from types import SimpleNamespace

from answer_engine import FAQEngine, BoundedWorker, phones, topics
from prepare_vector_db import read_training

BASE = Path(__file__).resolve().parent
records, incomplete = read_training(BASE / 'data' / 'data1.xlsx')


class Answers(unittest.TestCase):
    def setUp(self):
        self.engine = FAQEngine(records)

    def test_reported_wrong_price(self):
        answer, rows = self.engine.direct('giá Samsung Galaxy S26 Ultra là bao nhiêu')
        self.assertIn('31.490.000', answer)
        self.assertEqual(rows, [100])
        for q in ['giá iPhone 17 là bao nhiêu',
                  'iPhone 17 có giá tiền là bao nhiêu',
                  'gia iphone 17', 'iPhone 17 bao nhiêu tiền']:
            answer, rows = self.engine.direct(q)
            self.assertIn('Chưa có dữ liệu về giá', answer)
            self.assertEqual(rows, [])
            self.assertNotIn('Phù hợp', answer)

    def test_model_aliases_and_variants(self):
        for text, expected in [('S26 Ultra', 's26ultra'), ('Samsung Galaxy S26 FE', 's26fe'),
                               ('S26+', 's26+'), ('S26 Plus', 's26+'),
                               ('iPhone 17 Pro Max', 'iphone17promax'),
                               ('iPhone 17e', 'iphone17e'), ('Fold8', 'zfold8')]:
            self.assertEqual(set(phones(text)), {expected})
        self.assertNotEqual(phones('S26'), phones('S26 Ultra'))

    def test_ram_and_price(self):
        self.assertEqual(self.engine.direct('RAM của iphone 17')[1], [21])
        self.assertEqual(self.engine.direct('giá bán iphone 15')[1], [73])
        self.assertEqual(self.engine.direct('s26 ultra có spen không')[1], [99])

    def test_multi_attribute_missing_price(self):
        answer, rows = self.engine.direct('iPhone 17 giá và pin bao nhiêu')
        self.assertEqual(rows, [756])
        self.assertIn('Chưa có dữ liệu về giá', answer)

    def test_no_variant_crossover(self):
        for q, wanted in [('RAM S26 FE', 's26fe'), ('RAM S26 Ultra', 's26ultra'),
                          ('RAM S26 Plus', 's26+'), ('RAM iPhone 17 Pro', 'iphone17pro')]:
            _, rows = self.engine.direct(q)
            self.assertTrue(rows)
            for record in records:
                if record['row'] in rows:
                    self.assertEqual(set(phones(record['question'])), {wanted})

    def test_unknown_and_partial_models(self):
        self.assertIn('Chưa có dữ liệu', self.engine.direct('giá iPhone 12')[0])
        self.assertEqual(self.engine.direct('so sánh Redmi Note với S26 Ultra')[1], [])
        self.assertEqual(self.engine.direct('RAM của máy này')[1], [])

    def test_comparison(self):
        answer, rows = self.engine.direct('so sánh iPhone 16 Pro với iPhone 17 Pro')
        self.assertIn(55, rows)
        self.assertIn(26, rows)
        self.assertNotIn(31, rows)
        self.assertIn('iphone 16 pro:', answer)
        self.assertIn('iphone 17 pro:', answer)

    def test_all_exact_faqs(self):
        for record in records:
            with self.subTest(row=record['row']):
                answer, rows = self.engine.direct(record['question'])
                self.assertTrue(answer)
                self.assertTrue(rows)
                self.assertTrue(any(r['answer'].strip() == answer for r in records if r['row'] in rows)
                                or 'nhiều đáp án' in answer)

    def test_no_answer_text_entity_matching(self):
        doc = SimpleNamespace(metadata={'question': 'S26 FE phù hợp nhu cầu nào?',
                                         'answer': 'Gần S26 Ultra', 'row': 108})
        self.assertEqual(self.engine.safe_documents('giá S26 Ultra', [doc]), [])

    def test_deadline_and_no_concurrent_generation(self):
        worker = BoundedWorker()
        release = threading.Event()
        finished = threading.Event()
        def slow(deadline):
            release.wait(2)
            finished.set()
            return ('late', [])
        start = time.monotonic()
        self.assertEqual(worker.run(slow, ('fallback', []), .04), ('fallback', []))
        self.assertLess(time.monotonic() - start, .5)
        self.assertEqual(worker.run(lambda _: self.fail('Concurrent job'), ('busy', []), .04), ('busy', []))
        release.set()
        self.assertTrue(finished.wait(1))
        worker.gate.acquire(timeout=1)
        worker.gate.release()
        self.assertEqual(worker.run(lambda _: ('ready', []), ('fallback', []), 1), ('ready', []))


class WebRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ['MONGODB_URI'] = ''
        cls.storage = tempfile.TemporaryDirectory()
        os.environ['PHONEGPT_DB_FILE'] = str(Path(cls.storage.name) / 'test.db')
        import app
        cls.module = app
        cls.client = browser_client(app.app)
        with cls.client.session_transaction() as session:
            authenticated_session(app.app, session, 'local_regression_test')

    @classmethod
    def tearDownClass(cls):
        cls.storage.cleanup()
        os.environ.pop('PHONEGPT_DB_FILE', None)

    def test_budget_followup_and_new_chat(self):
        history = ['tôi có 15tr tôi muốn 1 chiếc điện thoại chơi game tốt điện thoại nào cũng được']
        body = self.client.post('/api/chat', json={'question': history[0]}).get_json()
        self.assertTrue(body['sources'])
        self.assertNotIn('Bạn cho mình tên', body['answer'])
        followed = self.client.post('/api/chat', json={
            'question': 'iphone 15 pro', 'question_history': history}).get_json()
        self.assertIn('chưa thể xác nhận', followed['answer'])
        self.assertIn(82, followed['sources'])
        streamed = self.client.post('/api/chat_stream', json={
            'question': 'iphone 15 pro', 'question_history': history})
        events = [json.loads(line[6:]) for line in streamed.get_data(as_text=True).splitlines()
                  if line.startswith('data: ')]
        self.assertEqual(''.join(e['text'] for e in events if e['type'] == 'token'), followed['answer'])
        fresh = self.client.post('/api/chat', json={'question': 'iphone 15 pro', 'question_history': []}).get_json()
        self.assertIn('Bạn muốn biết', fresh['answer'])
        self.assertEqual(fresh['sources'], [])
        self.assertIsNone(self.module.llm)

    def test_json_and_stream_match(self):
        question = 'giá iPhone 17 là bao nhiêu'
        response = self.client.post('/api/chat', json={'question': question})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        streamed = self.client.post('/api/chat_stream', json={'question': question})
        events = [json.loads(line[6:]) for line in streamed.get_data(as_text=True).splitlines()
                  if line.startswith('data: ')]
        self.assertEqual(''.join(e['text'] for e in events if e['type'] == 'token'), body['answer'])
        self.assertEqual(events[-1]['type'], 'done')
        self.assertEqual(body['sources'], [])
        self.assertIsNone(self.module.llm)

        priced = self.client.post('/api/chat', json={'question': 'giá Samsung Galaxy S26 Ultra là bao nhiêu'}).get_json()
        self.assertEqual(priced['sources'], [100])
        self.assertIn('31.490.000', priced['answer'])

    def test_screenshot_new_budget_request_drops_partial_comparison(self):
        question = 'Tôi có 15 triệu, muốn điện thoại chơi game tốt'
        prior = ['so sánh Redmi Note với Samsung Galaxy S26 Ultra']
        expected = self.client.post('/api/chat', json={'question': question}).get_json()
        payload = {'question': question, 'question_history': prior}
        actual = self.client.post('/api/chat', json=payload).get_json()
        self.assertEqual(actual['answer'], expected['answer'])
        self.assertEqual(actual['sources'], expected['sources'])
        self.assertTrue(actual['sources'])
        self.assertNotIn(101, actual['sources'])
        self.assertNotIn('s26 ultra', actual['answer'].lower())
        streamed = self.client.post('/api/chat_stream', json=payload)
        events = [json.loads(line[6:]) for line in streamed.get_data(as_text=True).splitlines()
                  if line.startswith('data: ')]
        self.assertEqual(''.join(e['text'] for e in events if e['type'] == 'token'), expected['answer'])

    def test_new_comparison_not_limited_by_previous_budget(self):
        question = 'so sánh iphone 17 pro max và iphone 12 pro max'
        prior = ['Tôi có 15 triệu, muốn điện thoại chơi game tốt']
        expected = self.client.post('/api/chat', json={'question': question}).get_json()
        actual = self.client.post('/api/chat', json={
            'question': question, 'question_history': prior}).get_json()
        self.assertEqual(actual['answer'], expected['answer'])
        self.assertEqual(actual['sources'], expected['sources'])
        self.assertNotIn('ngân sách', actual['answer'])

    def test_camera_budget_and_short_reply_recommend_models(self):
        initial = 'tôi có 10tr điện thoại nào chụp hình tốt'
        first = self.client.post('/api/chat', json={'question': initial}).get_json()
        self.assertEqual(first['status'], 'ok')
        self.assertEqual(set(first['sources']), {195, 193, 188, 186})
        self.assertNotIn('Bạn cho mình tên', first['answer'])
        followup = self.client.post('/api/chat', json={
            'question': 'chụp ảnh', 'question_history': [initial]}).get_json()
        self.assertEqual(followup['sources'], first['sources'])
        self.assertIn('10 triệu', followup['answer'])

    def test_input_and_login(self):
        self.assertEqual(self.client.post('/api/chat', json={'question': ''}).status_code, 400)
        anonymous = browser_client(self.module.app)
        self.assertEqual(anonymous.post('/api/chat', json={'question': 'hello'}).status_code, 401)

    def test_model_timeout_returns_complete_source(self):
        question = 'Snapdragon hoạt động thế nào?'
        doc = SimpleNamespace(metadata={'question': 'Snapdragon hoạt động như thế nào?',
                              'answer': 'Đây là đáp án đầy đủ lấy từ nguồn thử nghiệm.', 'row': 2},
                              page_content='Thông tin kiểm thử.')
        finished = threading.Event()
        def slow_stream(*args, **kwargs):
            time.sleep(.15)
            finished.set()
            yield 'Câu trả lời đang dang dở'
        model = SimpleNamespace(client=slow_stream)
        template = SimpleNamespace(format=lambda **_: 'prompt')
        database = SimpleNamespace(similarity_search=lambda *a, **k: [doc])
        with patch.object(self.module, 'get_database', return_value=database), \
             patch.object(self.module, 'get_model', return_value=(model, template)), \
             patch.object(self.module, 'fit_context', return_value=('context', [doc])), \
             patch.object(self.module, 'RESPONSE_BUDGET_SECONDS', .04):
            start = time.monotonic()
            result = self.client.post('/api/chat', json={'question': question}).get_json()
            self.assertLess(time.monotonic() - start, .5)
            self.assertEqual(result['answer'], doc.metadata['answer'])
            self.assertEqual(result['sources'], [2])
            self.assertTrue(finished.wait(1))

    def test_real_sse_streaming_and_midstream_timeout_replace(self):
        question = 'Snapdragon hoạt động thế nào?'
        doc = SimpleNamespace(metadata={'question': 'Snapdragon hoạt động như thế nào?',
                              'answer': 'Đây là đáp án đầy đủ lấy từ nguồn thử nghiệm.', 'row': 2},
                              page_content='Thông tin kiểm thử.')
        template = SimpleNamespace(format=lambda **_: 'prompt')
        database = SimpleNamespace(similarity_search=lambda *a, **k: [doc])

        def multi_chunk_stream(*args, **kwargs):
            yield 'Snapdragon '
            yield 'là vi xử lý di động.'

        model_ok = SimpleNamespace(client=multi_chunk_stream)
        with patch.object(self.module, 'get_database', return_value=database), \
             patch.object(self.module, 'get_model', return_value=(model_ok, template)), \
             patch.object(self.module, 'fit_context', return_value=('context', [doc])):
            streamed = self.client.post('/api/chat_stream', json={'question': question})
            events = [json.loads(line[6:]) for line in streamed.get_data(as_text=True).splitlines()
                      if line.startswith('data: ')]
            token_events = [e['text'] for e in events if e['type'] == 'token']
            self.assertEqual(token_events, ['Snapdragon ', 'là vi xử lý di động.'])
            self.assertEqual(events[0]['type'], 'sources')
            self.assertEqual(events[-1]['type'], 'done')

        finished = threading.Event()
        def slow_midstream(*args, **kwargs):
            yield 'Đoạn dở dang '
            time.sleep(.15)
            finished.set()
            yield 'phần sau.'

        model_slow = SimpleNamespace(client=slow_midstream)
        with patch.object(self.module, 'get_database', return_value=database), \
             patch.object(self.module, 'get_model', return_value=(model_slow, template)), \
             patch.object(self.module, 'fit_context', return_value=('context', [doc])), \
             patch.object(self.module, 'RESPONSE_BUDGET_SECONDS', .04):
            streamed = self.client.post('/api/chat_stream', json={'question': question})
            events = [json.loads(line[6:]) for line in streamed.get_data(as_text=True).splitlines()
                      if line.startswith('data: ')]
            self.assertTrue(any(e['type'] == 'token' and e['text'] == 'Đoạn dở dang ' for e in events))
            replaces = [e['text'] for e in events if e['type'] == 'replace']
            self.assertEqual(replaces, [doc.metadata['answer']])
            self.assertTrue(finished.wait(1))

    def test_frontend_caches_csrf_and_streams_without_fake_delay(self):
        html = (BASE / 'templates' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('cachedCsrfToken', html)
        self.assertIn("event.type === 'replace'", html)
        self.assertIn('typeTextSmoothly', html)


if __name__ == '__main__':
    unittest.main(verbosity=2)
