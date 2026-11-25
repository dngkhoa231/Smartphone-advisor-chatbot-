"""Regression checks for database failures and hostile request inputs."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from pymongo.errors import AutoReconnect
import app as chatbot
from test_client_helpers import browser_client, authenticated_session


class ProjectQuality(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        for name, value in (
            ('LOCAL_DB_FILE', str(Path(self.directory.name) / 'test.db')),
            ('users_collection', None), ('chat_collection', None),
        ):
            patcher = patch.object(chatbot, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        chatbot.init_sqlite()
        self.client = browser_client(chatbot.app)
        with self.client.session_transaction() as session:
            authenticated_session(chatbot.app, session, 'alice')

    def test_unicode_csrf_rejected_without_server_error(self):
        client = chatbot.app.test_client()
        client.get('/api/csrf')
        response = client.post('/api/logout', headers={'X-CSRF-Token': 'á'})
        self.assertEqual(response.status_code, 403)

    def test_ipv6_loopback_host_is_supported(self):
        self.assertEqual(self.client.get('/api/me', base_url='http://[::1]').status_code, 200)

    def test_mongo_read_failure_is_visible(self):
        collection = Mock()
        collection.find.side_effect = AutoReconnect('private driver details')
        with patch.object(chatbot, 'chat_collection', collection):
            response = self.client.get('/api/history')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private driver details', response.get_data(as_text=True))

    def test_mongo_write_failure_does_not_store_shadow_history(self):
        collection = Mock()
        collection.insert_one.side_effect = AutoReconnect('unavailable')
        with patch.object(chatbot, 'chat_collection', collection):
            with self.assertRaises(AutoReconnect):
                chatbot.save_chat_db({'username': 'alice'})
        with closing(sqlite3.connect(chatbot.LOCAL_DB_FILE)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM chat_history').fetchone()[0], 0)

    def test_failed_history_save_is_reported_in_json_and_stream(self):
        for route in ('/api/chat', '/api/chat_stream'):
            with self.subTest(route=route), patch.object(chatbot, 'answer_question', return_value=('Câu trả lời.', [])), patch.object(chatbot, 'save_chat_db', side_effect=sqlite3.OperationalError('secret-db-details')):
                response = self.client.post(route, json={'question': 'xin chào'})
                body = response.get_data(as_text=True)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn('secret-db-details', body)
                if route.endswith('stream'):
                    events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith('data: ')]
                    self.assertFalse(events[-1]['history_saved'])
                else:
                    self.assertFalse(response.get_json()['history_saved'])

    def test_session_database_failure_returns_json_503(self):
        with patch('security_controls.session_connection', side_effect=sqlite3.OperationalError('private')):
            response = self.client.get('/api/me')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()['status'], 'error')

    def test_corrupt_password_hash_does_not_crash_login(self):
        with patch.object(chatbot, 'get_user_db', return_value={'password': None}):
            response = self.client.post('/api/login', json={'username': 'bad-hash', 'password': 'any-password'})
        self.assertEqual(response.status_code, 401)

    def test_sql_injection_username_cannot_authenticate(self):
        response = self.client.post('/api/login', json={'username': "' OR 1=1 --", 'password': 'any-password'})
        self.assertEqual(response.status_code, 401)


if __name__ == '__main__':
    unittest.main()
