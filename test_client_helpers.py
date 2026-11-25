"""Browser-like CSRF handling for integration tests; production checks stay enabled."""
from flask.testing import FlaskClient

class BrowserClient(FlaskClient):
    def open(self, *args, **kwargs):
        if kwargs.get('method','GET').upper() in {'POST','PUT','PATCH','DELETE'}:
            token=super().open('/api/csrf',method='GET').get_json()['csrf_token']
            kwargs['headers']={**dict(kwargs.get('headers',{})), 'X-CSRF-Token':token}
        return super().open(*args,**kwargs)

def browser_client(app):
    return BrowserClient(app,app.response_class)

def authenticated_session(app,session,username):
    from security_controls import issue_token
    session['username']=username
    session['sid']=issue_token(app.extensions['security_database_path'](),username)
