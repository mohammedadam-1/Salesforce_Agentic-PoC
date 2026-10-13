"""Local, single-user OAuth authorization-code + PKCE helper."""
import base64,hashlib,json,os,pathlib,re,secrets,tempfile,time
from urllib.parse import urlencode,urlsplit
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
load_dotenv()
app=FastAPI(docs_url=None,redoc_url=None)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1'])
pending={}
TOKEN_FILE=pathlib.Path(__file__).parent/'.oauth_tokens.json'
COOKIE='sf_oauth_state'

def config():
 client=os.getenv('SALESFORCE_CLIENT_ID','').strip()
 if not client:raise HTTPException(503,'Set SALESFORCE_CLIENT_ID in .env, then restart.')
 login=os.getenv('SALESFORCE_LOGIN_URL','https://test.salesforce.com').rstrip('/')
 parsed=urlsplit(login)
 if parsed.scheme!='https' or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password or parsed.port or not (parsed.hostname and (parsed.hostname in ['login.salesforce.com','test.salesforce.com'] or parsed.hostname.endswith('.my.salesforce.com'))):raise HTTPException(503,'Invalid Salesforce login URL.')
 callback=os.getenv('SALESFORCE_REDIRECT_URI','http://localhost:8000/oauth/callback')
 if callback not in ['http://localhost:8000/oauth/callback','http://127.0.0.1:8000/oauth/callback']:raise HTTPException(503,'This helper supports local port 8000 callbacks only.')
 return client,login,callback

def challenge(verifier):return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
                        
def save_tokens(payload):
 if not isinstance(payload.get('access_token'),str) or not payload['access_token']:raise ValueError('Missing access token')
 instance=payload.get('instance_url','')
 if not re.fullmatch(r'https://[A-Za-z0-9.-]+\.salesforce\.com',instance):raise ValueError('Invalid instance URL')
 # File replaces previous authorization atomically; never retain an old user's refresh token.
 fd,name=tempfile.mkstemp(dir=TOKEN_FILE.parent,prefix='.oauth-')
 try:
  with os.fdopen(fd,'w') as f:json.dump({k:payload[k] for k in ['access_token','refresh_token','instance_url','issued_at','token_type','scope'] if k in payload},f)
  os.chmod(name,0o600);os.replace(name,TOKEN_FILE)
 finally:
  if os.path.exists(name):os.unlink(name)

@app.middleware('http')
async def private_headers(request,call_next):
 response=await call_next(request);response.headers['Cache-Control']='no-store';response.headers['Referrer-Policy']='no-referrer';response.headers['X-Content-Type-Options']='nosniff';return response

@app.get('/',response_class=HTMLResponse)
async def home():return '<h2>Salesforce PoC login</h2><p>Local development only.</p><a href="/login">Sign in to Salesforce</a>'

@app.get('/login')
async def login():
 client,origin,callback=config()
 for s in list(pending):
  if pending[s]['expires']<time.time():pending.pop(s)
 if len(pending)>=100:raise HTTPException(429,'Too many pending logins. Retry later.')
 state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
 pending[state]={'verifier':verifier,'expires':time.time()+600,'client':client,'origin':origin,'callback':callback}
 response=RedirectResponse(origin+'/services/oauth2/authorize?'+urlencode({'response_type':'code','client_id':client,'redirect_uri':callback,'scope':'api mcp_api refresh_token','state':state,'code_challenge':challenge(verifier),'code_challenge_method':'S256'}),status_code=302)
 response.set_cookie(COOKIE,state,httponly=True,samesite='lax',secure=False,max_age=600,path='/oauth')
 return response

@app.get('/oauth/callback')
async def callback(request:Request,state:str='',code:str='',error:str=''):
 cookie=request.cookies.get(COOKIE,'')
 if not state or not cookie or not secrets.compare_digest(state,cookie):raise HTTPException(400,'OAuth state mismatch. Start again at /login.')
 transaction=pending.pop(state,None)
 if not transaction or transaction['expires']<time.time():raise HTTPException(400,'Login expired or already used. Start again.')
 if error:raise HTTPException(400,'Salesforce authorization was declined or failed. Start again.')
 if not code:raise HTTPException(400,'Missing authorization code.')
 data={'grant_type':'authorization_code','client_id':transaction['client'],'code':code,'redirect_uri':transaction['callback'],'code_verifier':transaction['verifier']}
 if os.getenv('SALESFORCE_CLIENT_SECRET'):data['client_secret']=os.environ['SALESFORCE_CLIENT_SECRET']
 try:
  async with httpx.AsyncClient(timeout=30,follow_redirects=False) as client:
   response=await client.post(transaction['origin']+'/services/oauth2/token',data=data)
   response.raise_for_status();payload=response.json()
  save_tokens(payload)
 except Exception:raise HTTPException(502,'Token exchange or local saving failed. Check callback, client configuration, PKCE and org; start login again.') from None
 response=RedirectResponse('/connected',status_code=303);response.delete_cookie(COOKIE,path='/oauth');return response

@app.get('/connected',response_class=HTMLResponse)
async def connected():
 return '<h2>Login flow completed</h2><p>Tokens are stored locally and are not displayed. Run <code>python poc.py --preflight</code> from this project. No object has been created by logging in.</p>'
