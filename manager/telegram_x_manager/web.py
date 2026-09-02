from __future__ import annotations
import json, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

_state = {"running": False, "message": "Ready."}
_lock = threading.Lock()
_report = {}

def _status_loop():
    global _report
    from .health import run_checks
    while True:
        try:
            result = run_checks()
            with _lock: _report = result
        except Exception:
            pass
        threading.Event().wait(5)

HTML = '''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Telegram-X Manager</title>
<style>
:root{color-scheme:dark;--bg:#0b0e12;--panel:#141920;--panel2:#191f27;--line:#29323d;--text:#edf2f7;--muted:#8f9dab;--blue:#3b82f6;--green:#35c77a;--red:#f06b6b;--amber:#eab85a}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px Inter,ui-sans-serif,system-ui,sans-serif;letter-spacing:0}.shell{max-width:1180px;margin:auto;padding:24px}.topbar{display:flex;align-items:center;justify-content:space-between;padding-bottom:20px;border-bottom:1px solid var(--line)}.brand{display:flex;align-items:center;gap:12px}.logo{width:38px;height:38px;border-radius:8px;background:var(--blue);display:grid;place-items:center;font-weight:800;font-size:17px}.brand h1{font-size:18px;margin:0}.brand p{margin:3px 0 0;color:var(--muted);font-size:12px}.live{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:12px}.live i{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 0 4px #35c77a22}.notice{margin:18px 0;padding:13px 15px;background:#111b27;border:1px solid #244466;border-left:3px solid var(--blue);border-radius:6px;color:#c5d4e3;min-height:46px;display:flex;align-items:center}.notice.busy{border-color:#735b2d;border-left-color:var(--amber);background:#1b1811}.section-title{display:flex;justify-content:space-between;align-items:end;margin:24px 0 10px}.section-title h2{font-size:13px;text-transform:uppercase;color:#b7c1cb;margin:0}.section-title span{font-size:12px;color:var(--muted)}.status-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px;min-height:132px}.card-head{display:flex;justify-content:space-between;gap:8px;color:#b9c4ce;text-transform:capitalize}.dot{width:9px;height:9px;border-radius:50%;background:var(--red);margin-top:4px}.dot.ok{background:var(--green)}.value{font-size:18px;font-weight:700;margin:20px 0 8px}.value.ok{color:var(--green)}.value.bad{color:var(--red)}.detail{color:var(--muted);font-size:12px;line-height:1.45;overflow-wrap:anywhere}.workspace{display:grid;grid-template-columns:1.2fr .8fr;gap:14px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px}.panel h3{font-size:15px;margin:0 0 5px}.panel>p{color:var(--muted);margin:0 0 17px;font-size:12px}.form-row{display:grid;grid-template-columns:1fr 1fr 90px;gap:8px;margin-bottom:9px}.form-row.two{grid-template-columns:1fr 1fr}input{width:100%;height:40px;background:#0e1319;color:var(--text);border:1px solid #34404c;border-radius:6px;padding:0 11px;outline:none}input:focus{border-color:var(--blue);box-shadow:0 0 0 2px #3b82f622}button{height:40px;border:1px solid transparent;border-radius:6px;padding:0 14px;background:#242c35;color:var(--text);font-weight:650;cursor:pointer}button:hover{background:#303a45}button.primary{background:var(--blue)}button.primary:hover{background:#2f73dc}button.success{background:#167747}button.danger{background:#8d3338}button:disabled{opacity:.45;cursor:not-allowed}.button-row{display:flex;gap:8px;flex-wrap:wrap}.button-row button{flex:1;min-width:120px}.divider{height:1px;background:var(--line);margin:18px 0}.hint{font-size:11px;color:var(--muted);margin-top:8px}@media(max-width:850px){.status-grid{grid-template-columns:repeat(2,1fr)}.workspace{grid-template-columns:1fr}}@media(max-width:520px){.shell{padding:16px}.status-grid{grid-template-columns:1fr}.form-row,.form-row.two{grid-template-columns:1fr}.topbar{align-items:flex-start}.live{margin-top:6px}}
</style></head><body><main class="shell"><header class="topbar"><div class="brand"><div class="logo">TX</div><div><h1>Telegram-X Manager</h1><p>Local worker control center</p></div></div><div class="live"><i></i> Local service</div></header><div class="notice" id="message">Loading current status...</div><div class="section-title"><h2>System status</h2><span>Updates automatically</span></div><div class="status-grid" id="cards"></div><div class="section-title"><h2>Configuration and controls</h2></div><div class="workspace"><section class="panel"><h3>Connection setup</h3><p>Connect to the worker machine and save Telegram credentials.</p><div class="form-row"><input id="host" placeholder="SSH host or alias"><input id="username" placeholder="Username (optional)"><input id="port" value="22" placeholder="Port"></div><button class="primary" onclick="submitConnect()">Connect SSH</button><div class="divider"></div><div class="form-row two"><input id="token" type="password" placeholder="Telegram bot token"><input id="chat_id" placeholder="Chat ID (optional)"></div><button class="primary" onclick="submitCreds()">Save credentials</button><div class="hint">Credentials remain stored on this computer.</div></section><section class="panel"><h3>Worker operations</h3><p>Authenticate, deploy, and control the remote service.</p><div class="button-row"><button class="primary action" onclick="act('xlogin')">Log into X</button><button class="action" onclick="act('sync')">Sync credentials</button></div><div class="divider"></div><div class="button-row"><button class="action" onclick="act('deploy')">Deploy worker</button><button class="success action" onclick="act('start')">Start</button><button class="danger action" onclick="act('stop')">Stop</button></div><div class="hint">Long-running actions continue in the background. Progress appears above.</div></section></div></main>
<script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function refresh(){try{let r=await fetch('/api/status');let d=await r.json(),m=document.getElementById('message');m.textContent=d.message;m.classList.toggle('busy',d.running);document.querySelectorAll('.action,button.primary').forEach(b=>b.disabled=d.running);document.getElementById('cards').innerHTML=Object.entries(d.report||{}).map(([k,v])=>`<article class="card"><div class="card-head"><span>${esc(k.replaceAll('_',' '))}</span><i class="dot ${v.ok?'ok':''}"></i></div><div class="value ${v.ok?'ok':'bad'}">${v.ok?'Ready':'Needs setup'}</div><div class="detail">${esc(v.detail||'No details available')}</div></article>`).join('')}catch(e){document.getElementById('message').textContent='Could not load status: '+e}}
async function post(a,body={}){await fetch('/api/action/'+a,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});refresh()}
function act(a){post(a)}function submitConnect(){let host=document.getElementById('host').value.trim();if(!host)return document.getElementById('host').focus();post('connect',{host,username:document.getElementById('username').value.trim(),port:document.getElementById('port').value||'22'})}function submitCreds(){let token=document.getElementById('token').value.trim();if(!token)return document.getElementById('token').focus();post('creds',{token,chat_id:document.getElementById('chat_id').value.trim()})}refresh();setInterval(refresh,3000)
</script></body></html>'''

def _start(action, data):
    with _lock:
        if _state['running']: return
        _state.update(running=True, message=f'{action} is running. Please wait...')
    def work():
        try:
            from . import activity
            if action == 'connect':
                from .remote import ConnectionProfile, save_profile, verify_connection
                p=ConnectionProfile(data['host'], data.get('username') or 'root', int(data.get('port') or 22)); verify_connection(p); save_profile(p)
            elif action == 'creds':
                from . import creds; creds.save(data['token'], data.get('chat_id',''))
            elif action == 'xlogin':
                from .session import xlogin; from . import config; xlogin(config.session_file_path(), config.browser_profile_dir())
            elif action == 'deploy':
                from .worker import WorkerController; WorkerController().deploy()
            elif action == 'sync':
                from .worker import WorkerController; WorkerController().sync_credentials()
            else:
                from .worker import WorkerController; WorkerController().run_action(action)
            msg=f'{action} completed successfully.'
        except Exception as e: msg=f'{action} failed: {e}'
        with _lock: _state.update(running=False, message=msg)
    threading.Thread(target=work, daemon=True).start()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        if self.path.startswith('/api/status'):
            with _lock: state=dict(_state)
            with _lock: report = dict(_report)
            flat={k:{'ok':bool(v.get('ok') or v.get('connected') or v.get('exists')),'detail':v.get('detail','')} for k,v in report.items() if isinstance(v,dict)}
            self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(json.dumps({'report':flat,**state}).encode()); return
        self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers(); self.wfile.write(HTML.encode())
    def do_POST(self):
        if self.path.startswith('/api/action/'):
            n=int(self.headers.get('Content-Length','0')); data=json.loads(self.rfile.read(n) or b'{}'); _start(self.path.rsplit('/',1)[-1],data); self.send_response(202); self.end_headers()
def run():
    threading.Thread(target=_status_loop, daemon=True).start()
    server=ThreadingHTTPServer(('127.0.0.1',8765),Handler); url='http://127.0.0.1:8765'; print(f'Manager web UI: {url}'); webbrowser.open(url); server.serve_forever()
