from test_client_helpers import browser_client
"""Authentication evidence using throwaway accounts and databases only."""
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch, Mock
from werkzeug.security import check_password_hash
import app as chatbot


class Authentication(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db = str(Path(self.directory.name) / 'accounts.db')
        self.patchers = [patch.object(chatbot, 'LOCAL_DB_FILE', self.db),
                         patch.object(chatbot, 'users_collection', None)]
        for p in self.patchers: p.start()
        chatbot.init_sqlite()
        self.client = browser_client(chatbot.app)
        self.password = ' ' + secrets.token_urlsafe(20) + ' '
        self.credentials = {'username': 'temporary-review-user', 'password': self.password}

    def tearDown(self):
        for p in reversed(self.patchers): p.stop()
        self.directory.cleanup()

    def test_hash_persistence_and_login_after_process_restart(self):
        response = self.client.post('/api/register', json=self.credentials)
        self.assertEqual(response.status_code, 200)
        with closing(sqlite3.connect(self.db)) as connection:
            stored = connection.execute('SELECT password FROM users').fetchone()[0]
        self.assertNotEqual(stored, self.password)
        self.assertTrue(stored.startswith('scrypt:'))
        self.assertTrue(check_password_hash(stored, self.password))
        self.assertNotIn(self.password.strip().encode(), Path(self.db).read_bytes())
        self.assertNotIn('password', response.get_json())
        code = "import app,json,sys; from test_client_helpers import browser_client; c=browser_client(app.app); r=c.post('/api/login',json=json.load(sys.stdin)); print('LOGIN_STATUS='+str(r.status_code))"
        env = dict(os.environ, PHONEGPT_DB_FILE=self.db, MONGODB_URI='', PYTHONIOENCODING='utf-8')
        result = subprocess.run([sys.executable, '-c', code], input=json.dumps(self.credentials),
                                text=True, capture_output=True, env=env, timeout=30)
        self.assertEqual(result.returncode, 0)
        self.assertIn('LOGIN_STATUS=200', result.stdout)

    def test_wrong_password_and_duplicate_cannot_replace_account(self):
        self.client.post('/api/register', json=self.credentials)
        other = dict(self.credentials, password=secrets.token_urlsafe(20))
        self.assertEqual(self.client.post('/api/register', json=other).status_code, 400)
        self.client.post('/api/logout')
        self.assertEqual(self.client.post('/api/login', json=other).status_code, 401)
        self.assertEqual(self.client.post('/api/login', json=self.credentials).status_code, 200)
        # Simulate another registration winning the race after the existence check.
        with patch.object(chatbot, 'get_user_db', return_value=None):
            self.assertEqual(self.client.post('/api/register', json=other).status_code, 409)
        self.assertEqual(self.client.post('/api/login', json=self.credentials).status_code, 200)

    def test_malformed_request_is_rejected(self):
        for payload in [[], {'username': [], 'password': 7}, {'username': 'x'}, None]:
            for route in ['/api/login', '/api/register']:
                self.assertEqual(self.client.post(route, json=payload).status_code, 400)

    def test_mongo_failure_does_not_create_shadow_sqlite_account(self):
        collection = Mock()
        collection.find_one.return_value = None
        collection.insert_one.side_effect = RuntimeError('unavailable')
        with patch.object(chatbot, 'users_collection', collection):
            self.assertEqual(self.client.post('/api/register', json=self.credentials).status_code, 503)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM users').fetchone()[0], 0)


if __name__ == '__main__': unittest.main()
