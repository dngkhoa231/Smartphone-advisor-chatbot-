"""Local-demo security controls; no credentials or chat content in audit events."""
import datetime
import hashlib
import hmac
import secrets
import sqlite3
import time
from urllib.parse import urlsplit
from flask import request, session, jsonify

def session_connection(path):
    con=sqlite3.connect(path,timeout=2)
    con.execute('CREATE TABLE IF NOT EXISTS active_sessions (digest TEXT PRIMARY KEY, username TEXT NOT NULL, expires INTEGER NOT NULL)')
    return con

def issue_token(path,username):
    token=secrets.token_urlsafe(32);con=session_connection(path)
    try:
        con.execute('DELETE FROM active_sessions WHERE expires<=?',(int(time.time()),))
        con.execute('INSERT INTO active_sessions VALUES (?,?,?)',
                    (hashlib.sha256(token.encode()).hexdigest(),username,int(time.time())+1800))
        con.commit()
    finally:con.close()
    return token


def install_security(app, database_path):
    app.extensions['security_database_path']=database_path
    def revoke():
        token=session.get('sid')
        if token:
            con=session_connection(database_path())
            try:
                con.execute('DELETE FROM active_sessions WHERE digest=?',(hashlib.sha256(token.encode()).hexdigest(),));con.commit()
            finally:con.close()
        session.clear()
    def login(username):
        revoke()
        session.update(username=username,sid=issue_token(database_path(),username))
        session.permanent=True
    app.extensions['security_login']=login
    app.extensions['security_logout']=revoke
    app.config.update(MAX_CONTENT_LENGTH=32768, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Strict',
                      PERMANENT_SESSION_LIFETIME=datetime.timedelta(minutes=30))

    @app.get('/api/csrf')
    def csrf():
        session.setdefault('csrf', secrets.token_urlsafe(32))
        return jsonify(csrf_token=session['csrf'])

    @app.before_request
    def protect():
        if urlsplit(request.host_url).hostname not in {'localhost', '127.0.0.1', '::1'}:
            return jsonify(status='error', message='Host không được phép.'), 400
        if session.get('username'):
            token=session.get('sid','');con=session_connection(database_path())
            try:
                valid=con.execute('SELECT 1 FROM active_sessions WHERE digest=? AND username=? AND expires>?',
                                  (hashlib.sha256(token.encode()).hexdigest(),session['username'],int(time.time()))).fetchone()
            finally:con.close()
            if not valid:session.clear()
        if request.method in {'POST','PUT','PATCH','DELETE'}:
            origin=request.headers.get('Origin')
            if origin and origin != request.host_url.rstrip('/'):
                return jsonify(status='error', message='Nguồn yêu cầu không hợp lệ.'), 403
            token=request.headers.get('X-CSRF-Token','')
            if not token or not hmac.compare_digest(token.encode('utf-8'),session.get('csrf','').encode('utf-8')):
                return jsonify(status='error', message='Phiên yêu cầu hết hạn. Tải lại trang.'), 403
        if request.method=='POST' and request.path not in {'/api/logout'}:
            body=request.get_json(silent=True)
            if not isinstance(body,dict):
                return jsonify(status='error', message='Cần gửi một đối tượng JSON.'),400
            if request.path in {'/api/chat','/api/chat_stream'}:
                q=body.get('question');hist=body.get('question_history',[])
                if not isinstance(q,str) or not q.strip() or len(q)>2000:
                    return jsonify(status='error',message='Câu hỏi phải dài từ 1 đến 2000 ký tự.'),400
                if not isinstance(hist,list) or len(hist)>12 or any(not isinstance(x,str) or len(x)>2000 for x in hist):
                    return jsonify(status='error',message='Lịch sử gửi lên không hợp lệ.'),400
            if request.path=='/api/register':
                pw=body.get('password')
                if isinstance(pw,str) and len(pw)<12:
                    return jsonify(status='error',message='Mật khẩu cần ít nhất 12 ký tự.'),400
        if request.path in {'/api/login','/api/register','/api/chat','/api/chat_stream'} and request.method=='POST':
            # Persist counters across restarts. Hash keys; never store passwords/body.
            now=int(time.time());window=300 if request.path in {'/api/login','/api/register'} else 60
            limit=20 if window==300 else 30
            key=hashlib.sha256(((request.remote_addr or 'unknown')+'|'+request.path).encode()).hexdigest()
            con=sqlite3.connect(database_path(),timeout=2)
            try:
                con.execute('CREATE TABLE IF NOT EXISTS request_limits (key TEXT, bucket INTEGER, count INTEGER, PRIMARY KEY(key,bucket))')
                con.execute('BEGIN IMMEDIATE')
                bucket=(now//window)*window
                con.execute('DELETE FROM request_limits WHERE bucket < ?', (now-600,))
                row=con.execute('SELECT count FROM request_limits WHERE key=? AND bucket=?',(key,bucket)).fetchone()
                if row and row[0]>=limit:
                    con.rollback()
                    response=jsonify(status='error',message='Quá nhiều yêu cầu. Vui lòng thử lại sau.')
                    response.status_code=429;response.headers['Retry-After']=str(window-now%window)
                    return response
                con.execute('INSERT INTO request_limits VALUES (?,?,1) ON CONFLICT(key,bucket) DO UPDATE SET count=count+1',(key,bucket));con.commit()
            finally:con.close()

    @app.errorhandler(sqlite3.Error)
    def database_unavailable(error):
        app.logger.warning('security_database_unavailable')
        return jsonify(status='error', message='Dịch vụ tạm thời bận. Vui lòng thử lại.'), 503

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'"
        return response
