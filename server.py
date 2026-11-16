"""NyayaDesk self-hosted demo backend: stdlib Python + SQLite."""
import os, json, sqlite3, secrets, hashlib, hmac, time, mimetypes, pathlib, re, urllib.parse, urllib.request, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
ROOT=pathlib.Path(__file__).resolve().parent
DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
FILES=DATA/'uploads'; FILES.mkdir(exist_ok=True)
DB=DATA/'nyayadesk.sqlite3'; PORT=int(os.environ.get('PORT','8080'))
SESSIONS={}; LOCK=threading.RLock()
def conn():
 c=sqlite3.connect(DB,timeout=20);c.row_factory=sqlite3.Row;return c
def init():
 with conn() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE NOT NULL,salt TEXT NOT NULL,password TEXT NOT NULL);CREATE TABLE IF NOT EXISTS cases(user_id INTEGER PRIMARY KEY,payload TEXT NOT NULL);CREATE TABLE IF NOT EXISTS clients(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,name TEXT NOT NULL,email TEXT,phone TEXT,notes TEXT);CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,case_id INTEGER,description TEXT NOT NULL,due TEXT NOT NULL,done INTEGER DEFAULT 0);CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,case_id INTEGER NOT NULL,name TEXT NOT NULL,stored TEXT NOT NULL,mime TEXT,size INTEGER NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP);''')
def hashpass(p,s):return hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(s),260000).hex()
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def reply(self,status,obj,cookie=None):
  raw=json.dumps(obj).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"frame-ancestors 'none'")
  if cookie:self.send_header('Set-Cookie',cookie)
  self.end_headers();self.wfile.write(raw)
 def body(self,maxsize=4_000_000):
  n=int(self.headers.get('Content-Length','0'))
  if n<0 or n>maxsize:raise ValueError('Request exceeds size limit')
  return self.rfile.read(n)
 def jsonbody(self):return json.loads(self.body())
 def user(self):
  cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
  sid=cookie.get('nyayadesk_session'); item=SESSIONS.get(sid.value) if sid else None
  return item[0] if item and item[1]>time.time() else None
 def auth(self):
  uid=self.user()
  if uid is None:self.reply(401,{'error':'Please sign in'})
  return uid
 def route(self):
  path=urllib.parse.urlsplit(self.path).path
  if path=='/' or path=='/index.html':
   data=(ROOT/'index.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data);return
  if path=='/api/session':return self.reply(200,{'authenticated':bool(self.user())})
  if path in ('/api/register','/api/login') and self.command=='POST':
   b=self.jsonbody();email=str(b.get('email','')).strip().lower();password=str(b.get('password',''))
   if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email) or len(password)<10:return self.reply(400,{'error':'Enter a valid email and password of at least 10 characters'})
   with LOCK,conn() as c:
    if path.endswith('register'):
     salt=secrets.token_hex(16)
     try:c.execute('INSERT INTO users(email,salt,password) VALUES(?,?,?)',(email,salt,hashpass(password,salt)))
     except sqlite3.IntegrityError:return self.reply(409,{'error':'Account already exists'})
    row=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
    if not row or not hmac.compare_digest(hashpass(password,row['salt']),row['password']):return self.reply(401,{'error':'Incorrect credentials'})
   sid=secrets.token_urlsafe(32);SESSIONS[sid]=(row['id'],time.time()+86400)
   return self.reply(200,{'ok':True},f'nyayadesk_session={sid}; HttpOnly; SameSite=Lax; Path=/; Max-Age=86400')
  if path=='/api/logout' and self.command=='POST':
   cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''));v=cookie.get('nyayadesk_session')
   if v:SESSIONS.pop(v.value,None)
   return self.reply(200,{'ok':True},'nyayadesk_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0')
  if not path.startswith('/api/'):return self.reply(404,{'error':'Not found'})
  uid=self.auth()
  if uid is None:return
  if path=='/api/cases':
   if self.command=='GET':
    with conn() as c:r=c.execute('SELECT payload FROM cases WHERE user_id=?',(uid,)).fetchone()
    return self.reply(200,{'cases':json.loads(r['payload']) if r else None})
   if self.command=='PUT':
    b=self.jsonbody();items=b.get('cases')
    if not isinstance(items,list) or len(items)>5000:return self.reply(400,{'error':'Invalid case register'})
    with LOCK,conn() as c:c.execute('INSERT INTO cases(user_id,payload) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET payload=excluded.payload',(uid,json.dumps(items)))
    return self.reply(200,{'ok':True})
  if path in ('/api/clients','/api/reminders'):
   table=path.rsplit('/',1)[-1]
   if self.command=='GET':
    with conn() as c:rows=c.execute(f'SELECT * FROM {table} WHERE user_id=? ORDER BY id DESC',(uid,)).fetchall()
    return self.reply(200,{'items':[dict(x) for x in rows]})
   if self.command=='POST':
    b=self.jsonbody()
    with LOCK,conn() as c:
     if table=='clients':
      if not str(b.get('name','')).strip():return self.reply(400,{'error':'Client name required'})
      cur=c.execute('INSERT INTO clients(user_id,name,email,phone,notes) VALUES(?,?,?,?,?)',(uid,*[str(b.get(k,''))[:1000] for k in ('name','email','phone','notes')]))
     else:
      if not b.get('description') or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(b.get('due',''))):return self.reply(400,{'error':'Description and date required'})
      cur=c.execute('INSERT INTO reminders(user_id,case_id,description,due) VALUES(?,?,?,?)',(uid,b.get('case_id'),str(b['description'])[:1000],b['due']))
    return self.reply(201,{'id':cur.lastrowid})
   if self.command=='DELETE':
    rid=int(urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('id',['0'])[0]);
    with LOCK,conn() as c:c.execute(f'DELETE FROM {table} WHERE id=? AND user_id=?',(rid,uid))
    return self.reply(200,{'ok':True})
  if path=='/api/documents':
   if self.command=='GET':
    with conn() as c:rows=c.execute('SELECT id,case_id,name,mime,size,created FROM documents WHERE user_id=? ORDER BY id DESC',(uid,)).fetchall()
    return self.reply(200,{'items':[dict(x) for x in rows]})
   if self.command=='POST':
    qs=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query);case_id=int(qs.get('case_id',['0'])[0]);name=pathlib.Path(qs.get('name',['document'])[0]).name[:180];raw=self.body(10_000_000)
    mime=mimetypes.guess_type(name)[0] or 'application/octet-stream'
    if pathlib.Path(name).suffix.lower() not in ('.pdf','.doc','.docx','.png','.jpg','.jpeg','.txt'):return self.reply(400,{'error':'Unsupported file type'})
    stored=secrets.token_hex(24);(FILES/stored).write_bytes(raw)
    with LOCK,conn() as c:cur=c.execute('INSERT INTO documents(user_id,case_id,name,stored,mime,size) VALUES(?,?,?,?,?,?)',(uid,case_id,name,stored,mime,len(raw)))
    return self.reply(201,{'id':cur.lastrowid})
   if self.command=='DELETE':
    rid=int(urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('id',['0'])[0]);
    with LOCK,conn() as c:
     row=c.execute('SELECT stored FROM documents WHERE id=? AND user_id=?',(rid,uid)).fetchone();c.execute('DELETE FROM documents WHERE id=? AND user_id=?',(rid,uid))
    if row:(FILES/row['stored']).unlink(missing_ok=True)
    return self.reply(200,{'ok':True})
  if path.startswith('/api/documents/') and self.command=='GET':
   rid=int(path.rsplit('/',1)[-1]);
   with conn() as c:row=c.execute('SELECT * FROM documents WHERE id=? AND user_id=?',(rid,uid)).fetchone()
   if not row:return self.reply(404,{'error':'Document not found'})
   raw=(FILES/row['stored']).read_bytes();self.send_response(200);self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+urllib.parse.quote(row['name']));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
  if path=='/api/assistant' and self.command=='POST':
   b=self.jsonbody();question=str(b.get('question',''))[:2000];case=b.get('case') or {}
   prompt=f"Case: {case.get('num','Unknown')}. Stage: {case.get('stage','Not provided')}. Hearing: {case.get('date','Unknown')}. Acts: {case.get('acts','Not provided')}."
   key=os.environ.get('OPENAI_API_KEY')
   if not key:return self.reply(200,{'mode':'demo','answer':f"CASE CONTEXT\n{prompt}\n\nPROCEDURAL CHECKLIST\n1. Verify the latest official order and cause list.\n2. Confirm applicable procedural deadlines and service requirements.\n3. Prepare a chronology, indexed evidence and concise submissions.\n4. Research authoritative judgments on the exact legal issues raised.\n\nYOUR QUESTION\n{question}\n\nThis is a generic checklist, not case-specific legal advice. Configure OPENAI_API_KEY for model-assisted analysis; verify every citation independently."})
   req=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps({'model':os.environ.get('OPENAI_MODEL','gpt-4.1-mini'),'instructions':'You are a legal research assistant for Indian advocates. Give structured cautious analysis: known facts, issues, procedural next steps, research directions, uncertainties. Do not invent precedents or citations. Flag that all authorities and court information require verification.','input':prompt+'\nQuestion: '+question}).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
   try:
    with urllib.request.urlopen(req,timeout=35) as r:result=json.load(r)
    answer='\n'.join(part.get('text','') for item in result.get('output',[]) for part in item.get('content',[]) if part.get('type')=='output_text')
    return self.reply(200,{'mode':'ai','answer':answer or 'No text returned.'})
   except Exception:return self.reply(502,{'error':'AI provider unavailable. Please retry.'})
  return self.reply(404,{'error':'Endpoint not found'})
 def do_GET(self):
  try:self.route()
  except Exception as e:self.reply(400,{'error':str(e)[:180]})
 def do_POST(self):
  try:self.route()
  except Exception as e:self.reply(400,{'error':str(e)[:180]})
 def do_PUT(self):
  try:self.route()
  except Exception as e:self.reply(400,{'error':str(e)[:180]})
 def do_DELETE(self):
  try:self.route()
  except Exception as e:self.reply(400,{'error':str(e)[:180]})
if __name__=='__main__':
 init();print(f'NyayaDesk running at http://localhost:{PORT}',flush=True);ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
