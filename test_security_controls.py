import secrets
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app as chatbot

class SecurityControls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(chatbot,'LOCAL_DB_FILE',str(Path(self.temp.name)/'db.sqlite')),
                      patch.object(chatbot,'users_collection',None)]
        for p in self.patches:p.start()
        chatbot.init_sqlite();self.client=chatbot.app.test_client()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def headers(self):
        return {'X-CSRF-Token':self.client.get('/api/csrf').get_json()['csrf_token']}
    def test_csrf_and_origin(self):
        self.assertEqual(self.client.post('/api/logout').status_code,403)
        h=self.headers();h['Origin']='https://attacker.invalid'
        self.assertEqual(self.client.post('/api/logout',headers=h).status_code,403)
        self.assertEqual(self.client.post('/api/logout',headers=self.headers()).status_code,200)
    def test_persistent_rate_limit(self):
        data={'username':'unknown','password':secrets.token_urlsafe(16)}
        for _ in range(20):
            self.assertEqual(self.client.post('/api/login',headers=self.headers(),json=data).status_code,401)
        self.client=chatbot.app.test_client()
        r=self.client.post('/api/login',headers=self.headers(),json=data)
        self.assertEqual(r.status_code,429);self.assertIn('Retry-After',r.headers)
    def test_cookie_headers_and_host(self):
        r=self.client.get('/api/csrf');cookie=r.headers.get('Set-Cookie','')
        self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie)
        self.assertEqual(r.headers['X-Frame-Options'],'DENY')
        self.assertEqual(self.client.get('/',headers={'Host':'attacker.invalid'}).status_code,400)
    def test_payload_limits(self):
        for body in [{'question':[]},{'question':'x'*2001},{'question':'x','question_history':[3]}]:
            self.assertEqual(self.client.post('/api/chat',headers=self.headers(),json=body).status_code,400)
        self.assertEqual(self.client.post('/api/chat',headers=self.headers(),json={'question':'x'*40000}).status_code,413)
    def test_short_password_rejected(self):
        self.assertEqual(self.client.post('/api/register',headers=self.headers(),json={'username':'x','password':'short'}).status_code,400)

    def test_logged_out_cookie_cannot_be_replayed(self):
        data={'username':'replay-check','password':secrets.token_urlsafe(20)}
        self.assertEqual(self.client.post('/api/register',headers=self.headers(),json=data).status_code,200)
        old=self.client.get_cookie('session').value
        self.assertEqual(self.client.post('/api/logout',headers=self.headers()).status_code,200)
        attacker=chatbot.app.test_client();attacker.set_cookie('session',old)
        self.assertFalse(attacker.get('/api/me').get_json()['logged_in'])

    def test_expired_session_is_rejected_server_side(self):
        data={'username':'expiry-check','password':secrets.token_urlsafe(20)}
        self.client.post('/api/register',headers=self.headers(),json=data)
        con=sqlite3.connect(chatbot.LOCAL_DB_FILE)
        con.execute('UPDATE active_sessions SET expires=0');con.commit();con.close()
        self.assertFalse(self.client.get('/api/me').get_json()['logged_in'])

if __name__=='__main__':unittest.main()
