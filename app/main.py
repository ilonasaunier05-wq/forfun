import asyncio
import ipaddress
import json
import secrets
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from .config import ROOT
from .runtime import Runtime
from .tools import TOOL_SCHEMAS

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')
class Login(Input):
    password: str = Field(max_length=500)
class Chat(Input):
    session: str
    text: str = Field(min_length=1, max_length=12000)
    model: str | None = None
    speak: bool = True
class ToolCall(Input):
    name: str
    arguments: dict = Field(default_factory=dict)
class Confirmation(Input):
    id: str
    approved: bool
class Switch(Input):
    enabled: bool
class Speak(Input):
    text: str = Field(min_length=1, max_length=4000)
class VoiceSettings(Input):
    language: str
    voice: str = ''
class Memory(Input):
    content: str = Field(min_length=1, max_length=4000)
    category: str = 'Preferences'
    confirmed: bool = False


def create_app(runtime=None):
    rt = runtime or Runtime()
    settings, store = rt.settings, rt.store
    sessions, attempts = {}, {}
    background = set()
    @asynccontextmanager
    async def lifespan(app):
        yield
        for task in background: task.cancel()
        if background: await asyncio.gather(*background, return_exceptions=True)
        await rt.close()
    app = FastAPI(title='Jarvis', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.runtime = rt

    @app.middleware('http')
    async def security(request, call_next):
        if (request.url.hostname or '').lower() not in settings.allowed_hosts:
            return JSONResponse({'detail':'Host not allowlisted'},status_code=403)
        origin = request.headers.get('origin')
        if origin and origin != f'{request.url.scheme}://{request.headers.get("host")}':
            return JSONResponse({'detail':'Cross-origin requests disabled'},status_code=403)
        if request.method in {'POST','PUT','PATCH'} and request.headers.get('content-type','').split(';')[0] != 'application/json':
            return JSONResponse({'detail':'JSON content type required'},status_code=415)
        try: loopback = ipaddress.ip_address(request.client.host).is_loopback
        except ValueError: loopback = False
        if not settings.password and not loopback:
            return JSONResponse({'detail':'Network access requires JARVIS_PASSWORD and trusted HTTPS'},status_code=403)
        if request.url.path.startswith('/api/') and request.url.path != '/api/login' and settings.password:
            if sessions.get(request.cookies.get('jarvis_session',''),0) < time.monotonic():
                return JSONResponse({'detail':'Sign in to Jarvis'},status_code=401)
        response = await call_next(request)
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"})
        return response

    @app.exception_handler(ValueError)
    @app.exception_handler(RuntimeError)
    async def error(request, exc):
        return JSONResponse({'detail':rt.safe_error(exc)},status_code=400)

    def launch(coro):
        task = asyncio.create_task(coro); background.add(task); task.add_done_callback(background.discard)
        return task

    @app.post('/api/login')
    async def login(body: Login, request: Request):
        recent = [x for x in attempts.get(request.client.host,[]) if time.monotonic()-x<60]
        attempts[request.client.host]=recent
        if len(recent)>=5: raise HTTPException(429,'Wait one minute before retrying login')
        recent.append(time.monotonic())
        if settings.password and not secrets.compare_digest(body.password.encode(),settings.password.encode()): raise HTTPException(401,'Incorrect password')
        token=secrets.token_urlsafe(32); sessions[token]=time.monotonic()+43200
        response=JSONResponse({'ok':True});response.set_cookie('jarvis_session',token,max_age=43200,httponly=True,secure=settings.secure_cookie,samesite='strict');return response

    @app.post('/api/logout')
    async def logout(request: Request):
        sessions.pop(request.cookies.get('jarvis_session',''),None)
        response=JSONResponse({'ok':True});response.delete_cookie('jarvis_session');return response

    @app.get('/api/config')
    def config():
        return {'model':settings.model,'fallback_model':settings.fallback_model,'key_configured':bool(settings.key),'language':settings.language,'voice':settings.voice,'notes_dir':str(settings.notes_dir),'projects_dir':str(settings.projects_dir),'apps':list(settings.app_config.get('apps',{})),'tools':[x['function']['name'] for x in TOOL_SCHEMAS],'categories':['Profile','Preferences','Home','Projects','Routines'],'scenes':{name:bool(plan.get('home') or plan.get('pc')) for name,plan in rt.tools.scenes().items()}}

    @app.get('/api/status')
    def status():
        return {**rt.tools.telemetry(),'microphone_error':rt.microphone_error,'microphone_ready':rt.mic.stream is not None,'voice_active':bool(rt.voice_task and not rt.voice_task.done()),'mic_level':rt.mic.last_level,'tts_backend':rt.speaker.backend,'tts_voice':rt.speaker.selected_voice}

    @app.get('/api/devices')
    async def devices(): return await rt.tools.devices()

    @app.post('/api/sessions')
    def new_session(): return {'id':store.session()}
    @app.get('/api/sessions')
    def session_list(): return store.rows('SELECT * FROM sessions ORDER BY created DESC')
    @app.get('/api/sessions/{sid}')
    def history(sid: str): return store.history(sid,10000)
    @app.delete('/api/sessions/{sid}')
    def delete_session(sid: str):
        if rt.turn_lock.locked(): raise ValueError('Finish active turn before deletion.')
        store.execute('DELETE FROM messages WHERE session=?',(sid,));store.execute('DELETE FROM sessions WHERE id=?',(sid,));return {'ok':True}
    @app.get('/api/export')
    def export(): return {'sessions':store.rows('SELECT * FROM sessions'),'messages':store.rows('SELECT * FROM messages'),'memories':store.rows('SELECT * FROM memories'),'memory_markdown':settings.memory_file.read_text(encoding='utf-8') if settings.memory_file.exists() else ''}
    @app.get('/api/memory-file')
    def memory_file():
        path=rt.tools.confined_write('memory.md')
        return {'content':path.read_text(encoding='utf-8') if path.exists() else ''}

    @app.get('/api/memories')
    def memories(q: str=''): return store.search(q) if q else store.rows('SELECT * FROM memories ORDER BY created DESC')
    @app.post('/api/memories')
    def add_memory(body: Memory):
        if not body.confirmed: raise ValueError('Confirm before storing memory.')
        return {'id':store.memory(body.content,body.category)}
    @app.put('/api/memories/{mid}')
    def edit_memory(mid: str, body: Memory):
        if not body.confirmed: raise ValueError('Confirm before editing memory.')
        return {'id':store.memory(body.content,body.category,mid)}
    @app.delete('/api/memories/{mid}')
    def forget(mid: str, request: Request):
        if request.headers.get('x-jarvis-confirm')!='yes': raise ValueError('Confirm before deleting memory.')
        store.forget(mid);return {'ok':True}

    @app.post('/api/tools')
    async def switch(body: Switch):
        settings.tools_enabled=body.enabled
        store.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('tools_enabled',str(body.enabled).lower()))
        if not body.enabled:
            rt.speaker.interrupt()
            for future,_ in rt.confirmations.values():
                if not future.done(): future.set_result(False)
        return {'enabled':body.enabled}

    @app.post('/api/confirm')
    async def confirm(body: Confirmation):
        rt.answer_confirmation(body.id,body.approved);return {'ok':True}

    @app.post('/api/tool')
    async def tool(body: ToolCall):
        rt.tools.validate(body.name,body.arguments)
        async def run():
            try:
                await rt.emit('tool_call',{'name':body.name,'arguments':body.arguments})
                await rt.emit('state','running_action')
                result=await rt.tools.call(body.name,body.arguments,lambda prompt:rt.confirm(prompt,'ui'))
                await rt.emit('tool_result',{'name':body.name,'result':result})
            except Exception as exc: await rt.emit('error',rt.safe_error(exc))
            finally: await rt.emit('state','idle')
        launch(run());return {'started':True}

    @app.post('/api/chat')
    async def chat(body: Chat):
        store.require_session(body.session)
        if not body.text.strip():raise ValueError('Message cannot be blank.')
        async def events():
            async for event in rt.chat(body.session,body.text,'ui',body.speak,body.model):
                yield 'data: '+json.dumps(event,ensure_ascii=False)+'\n\n'
        return StreamingResponse(events(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})

    @app.get('/api/events')
    async def events(request: Request):
        async def stream():
            q=asyncio.Queue(maxsize=200);rt.listeners.add(q)
            yield 'data: '+json.dumps({'type':'connected','data':True})+'\n\n'
            try:
                while not rt.stop.is_set() and not await request.is_disconnected():
                    try: event=await asyncio.wait_for(q.get(),15)
                    except asyncio.TimeoutError:
                        yield ': keepalive\n\n';continue
                    yield 'data: '+json.dumps(event,ensure_ascii=False)+'\n\n'
            finally:rt.listeners.discard(q)
        return StreamingResponse(stream(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})

    @app.post('/api/voice/listen')
    async def listen():
        if rt.voice_task and not rt.voice_task.done():
            rt.wake.set();return {'started':True}
        async def once():
            try:
                text=await rt.record_once();await rt.native_turn(text,'voice')
            except Exception as exc:await rt.emit('error',rt.safe_error(exc))
        launch(once());return {'started':True}
    @app.post('/api/voice/wake')
    async def wake(body: Switch):
        if body.enabled:
            await rt.start_voice()
        elif rt.voice_task:
            rt.voice_task.cancel();rt.wake.set()
            await asyncio.gather(rt.voice_task,return_exceptions=True);rt.voice_task=None
        return {'enabled':bool(rt.voice_task and not rt.voice_task.done())}
    @app.post('/api/voice/stop')
    async def stop():rt.speaker.interrupt();return {'ok':True}
    @app.post('/api/voice/speak')
    async def speak(body: Speak):
        launch(rt.soft_say(body.text));return {'started':True}
    @app.post('/api/voice/settings')
    async def voice_settings(body: VoiceSettings):
        if body.language not in {'en','fr'}:raise ValueError('Language must be en or fr.')
        if body.voice and not body.voice.endswith('Neural'):raise ValueError('Supply an Edge Neural voice name.')
        settings.language=body.language;settings.voice=body.voice or ('fr-FR-HenriNeural' if body.language=='fr' else 'en-GB-RyanNeural')
        return {'language':settings.language,'voice':settings.voice}
    @app.get('/')
    def index():return FileResponse(ROOT/'ui'/'index.html')
    app.mount('/ui',StaticFiles(directory=ROOT/'ui'),name='ui')
    return app
