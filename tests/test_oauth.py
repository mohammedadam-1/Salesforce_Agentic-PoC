import json,time
from urllib.parse import urlsplit,parse_qs
from fastapi.testclient import TestClient
import oauth_app as o

def setup(monkeypatch):
 monkeypatch.setenv('SALESFORCE_CLIENT_ID','test-client');monkeypatch.setenv('SALESFORCE_LOGIN_URL','https://test.salesforce.com');monkeypatch.setenv('SALESFORCE_REDIRECT_URI','http://localhost:8000/oauth/callback');o.pending.clear()
 return TestClient(o.app,base_url='http://localhost:8000')

def test_pkce_login(monkeypatch):
 c=setup(monkeypatch);r=c.get('/login',follow_redirects=False);q=parse_qs(urlsplit(r.headers['location']).query)
 assert r.status_code==302 and q['code_challenge_method']==['S256']
 assert q['code_challenge'][0]==o.challenge(o.pending[q['state'][0]]['verifier'])
 assert 'HttpOnly' in r.headers['set-cookie'] and 'no-store'==r.headers['cache-control']

def test_state_required(monkeypatch):
 c=setup(monkeypatch);assert c.get('/oauth/callback?state=fake&code=fake').status_code==400

def test_state_mismatch_does_not_consume(monkeypatch):
 c=setup(monkeypatch);c.get('/login',follow_redirects=False);s=next(iter(o.pending));assert c.get('/oauth/callback?state=wrong&code=x').status_code==400;assert s in o.pending

def test_expired_and_replay(monkeypatch):
 c=setup(monkeypatch);c.get('/login',follow_redirects=False);s=next(iter(o.pending));o.pending[s]['expires']=time.time()-1
 assert c.get('/oauth/callback',params={'state':s,'code':'x'}).status_code==400;assert s not in o.pending
 assert c.get('/oauth/callback',params={'state':s,'code':'x'}).status_code==400

def test_callback_exchange(monkeypatch,tmp_path):
 c=setup(monkeypatch);c.get('/login',follow_redirects=False);s=next(iter(o.pending));verifier=o.pending[s]['verifier'];monkeypatch.setattr(o,'TOKEN_FILE',tmp_path/'tokens.json')
 class Response:
  def raise_for_status(self):pass
  def json(self):return {'access_token':'private-token','instance_url':'https://example.my.salesforce.com','refresh_token':'refresh'}
 class Client:
  def __init__(self,**kw):pass
  async def __aenter__(self):return self
  async def __aexit__(self,*a):pass
  async def post(self,url,data):
   assert data['code_verifier']==verifier and data['grant_type']=='authorization_code';return Response()
 monkeypatch.setattr(o.httpx,'AsyncClient',Client)
 r=c.get('/oauth/callback',params={'state':s,'code':'x'},follow_redirects=False)
 assert r.status_code==303 and 'private-token' not in r.text
 assert json.loads(o.TOKEN_FILE.read_text())['access_token']=='private-token'
 assert c.get('/oauth/callback',params={'state':s,'code':'x'}).status_code==400

def test_untrusted_host(monkeypatch):
 c=setup(monkeypatch);assert c.get('/',headers={'Host':'attacker.example'}).status_code==400
