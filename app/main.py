import asyncio
import ipaddress
import json
import re
import secrets
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from .config import ROOT, Settings
from .store import Store, CATEGORIES, now
from .tools import Tools, SCENE_NAMES
from .providers import SYSTEM, search_web, stream_completion

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Login(Input):
    password: str = Field(max_length=500)

class Chat(Input):
    session: str
    text: str = Field(min_length=1, max_length=12000)
    provider: str = 'compatible'
    model: str = 'llama-3.3-70b-versatile'
    search: bool = False

class Memory(Input):
    content: str = Field(min_length=1, max_length=4000)
    category: str = 'Preferences'
    confirmed: bool = False

class Confirm(Input):
    confirmation: str = Field(max_length=100)

class Switch(Input):
    enabled: bool


def create_app(settings=None):
    settings = settings or Settings()
    store = Store(settings.data_dir)
    saved_tools = store.rows("SELECT value FROM settings WHERE key='tools_enabled'")
    if saved_tools:
        settings.tools_enabled = saved_tools[0]['value'] == 'true'
    tools = Tools(settings, store)
    auth_sessions = {}
    login_attempts = {}
    busy_sessions = set()
    semaphore = asyncio.Semaphore(2)

    @asynccontextmanager
    async def lifespan(app):
        yield
        store.db.close()

    app = FastAPI(title='JARVIS personal assistant', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store, app.state.tools, app.state.settings = store, tools, settings

    @app.middleware('http')
    async def security(request, call_next):
        host = request.url.hostname or ''
        if host.lower() not in settings.allowed_hosts:
            return JSONResponse({'detail': 'Host is not allowlisted'}, status_code=403)
        origin = request.headers.get('origin')
        if origin and origin != f'{request.url.scheme}://{request.headers.get("host")}':
            return JSONResponse({'detail': 'Cross-origin requests are disabled'}, status_code=403)
        if request.method in {'POST', 'PUT', 'PATCH'} and request.headers.get('content-type', '').split(';')[0] != 'application/json':
            return JSONResponse({'detail': 'JSON content type required'}, status_code=415)
        try:
            loopback = ipaddress.ip_address(request.client.host).is_loopback
        except ValueError:
            loopback = False
        if not settings.password and not loopback:
            return JSONResponse({'detail': 'LAN access requires JARVIS_PASSWORD'}, status_code=403)
        if request.url.path.startswith('/api/') and request.url.path != '/api/login' and settings.password:
            token = request.cookies.get('jarvis_session', '')
            if auth_sessions.get(token, 0) < time.monotonic():
                return JSONResponse({'detail': 'Sign in to JARVIS'}, status_code=401)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=400)

    @app.exception_handler(httpx_error_type())
    async def network_error(request, exc):
        return JSONResponse({'detail': 'Integration connection failed. Check endpoint, connectivity, and credentials.'}, status_code=502)

    @app.post('/api/login')
    def login(body: Login, request: Request):
        key = request.client.host
        timestamp = time.monotonic()
        attempts = [t for t in login_attempts.get(key, []) if timestamp - t < 60]
        login_attempts[key] = attempts
        if len(attempts) >= 5:
            raise HTTPException(429, 'Too many attempts; wait one minute')
        attempts.append(timestamp)
        if settings.password and not secrets.compare_digest(body.password.encode(), settings.password.encode()):
            raise HTTPException(401, 'Incorrect password')
        for token, expiry in list(auth_sessions.items()):
            if expiry < timestamp:
                auth_sessions.pop(token)
        token = secrets.token_urlsafe(32)
        auth_sessions[token] = timestamp + 12 * 3600
        response = JSONResponse({'ok': True})
        response.set_cookie('jarvis_session', token, httponly=True, secure=settings.secure_cookie, samesite='strict', max_age=12 * 3600)
        return response

    @app.post('/api/logout')
    def logout(request: Request):
        auth_sessions.pop(request.cookies.get('jarvis_session', ''), None)
        response = JSONResponse({'ok': True})
        response.delete_cookie('jarvis_session')
        return response

    @app.get('/api/config')
    def config():
        return {'free_mode': settings.free_mode, 'default_provider': 'compatible' if settings.free_mode else next(iter(settings.providers)), 'providers': {name: {'models': p['models'], 'configured': bool(p['key'])} for name, p in settings.providers.items()}, 'search_configured': bool(settings.search_key), 'categories': CATEGORIES, 'scenes': SCENE_NAMES, 'dry_run': settings.dry_run, 'tools_enabled': settings.tools_enabled, 'data_location': str(settings.data_dir), 'daily_request_limit': settings.daily_requests, 'daily_budget_usd': settings.daily_budget, 'max_output_tokens': settings.max_output}

    @app.post('/api/sessions')
    def new_session():
        return {'id': store.session()}

    @app.get('/api/sessions')
    def sessions():
        return store.rows('SELECT * FROM sessions ORDER BY created DESC')

    @app.get('/api/sessions/{sid}')
    def history(sid: str):
        return store.history(sid, 10000)

    @app.delete('/api/sessions/{sid}')
    def delete_session(sid: str):
        if sid in busy_sessions:
            raise ValueError('Stop the active response before deleting this conversation')
        store.execute('DELETE FROM messages WHERE session=?', (sid,))
        store.execute('DELETE FROM sessions WHERE id=?', (sid,))
        return {'ok': True}

    @app.get('/api/export')
    def export():
        return {'sessions': store.rows('SELECT * FROM sessions'), 'messages': store.rows('SELECT * FROM messages'), 'memories': store.rows('SELECT * FROM memories')}

    @app.get('/api/memories')
    def memories(q: str = ''):
        return store.search(q) if q else store.rows('SELECT * FROM memories ORDER BY created DESC')

    @app.post('/api/memories')
    def add_memory(body: Memory):
        if not body.confirmed:
            raise ValueError('Explicit confirmation is required before storing any long-term memory')
        return {'id': store.memory(body.content, body.category)}

    @app.put('/api/memories/{mid}')
    def edit_memory(mid: str, body: Memory):
        if not body.confirmed:
            raise ValueError('Explicit confirmation is required')
        return {'id': store.memory(body.content, body.category, mid)}

    @app.delete('/api/memories/{mid}')
    def delete_memory(mid: str):
        store.forget(mid)
        return {'ok': True}

    @app.get('/api/status')
    def status():
        return tools.telemetry()

    @app.get('/api/devices')
    async def devices():
        return await tools.devices()

    @app.post('/api/tools')
    def switch(body: Switch):
        settings.tools_enabled = body.enabled
        store.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('tools_enabled', str(body.enabled).lower()))
        tools.pending.clear()
        return {'enabled': body.enabled}

    @app.post('/api/actions/prepare')
    def prepare(body: dict):
        return tools.prepare(body)

    @app.post('/api/actions/execute')
    async def execute(body: Confirm):
        return await tools.execute(body.confirmation)

    @app.get('/api/actions')
    def action_log():
        return store.rows('SELECT * FROM actions ORDER BY id DESC LIMIT 100')

    @app.get('/api/usage')
    def usage(session: str = ''):
        args = (now()[:10],)
        clause = 'day=?'
        if session:
            clause += ' AND session=?'
            args += (session,)
        rows = store.rows('SELECT count(*) requests, coalesce(sum(input_tokens),0) input_tokens, coalesce(sum(output_tokens),0) output_tokens, coalesce(sum(coalesce(actual_cost,reserved_cost)),0) budget_used_usd, sum(actual_cost IS NULL) requests_without_priced_usage FROM usage WHERE ' + clause, args)
        return rows[0]

    @app.post('/api/chat')
    async def chat(body: Chat):
        store.require_session(body.session)
        if settings.free_mode and body.search:
            raise ValueError('Web search is disabled in free mode. No paid search request was sent.')
        if not body.text.strip():
            raise ValueError('Message cannot be blank')
        if body.session in busy_sessions:
            raise HTTPException(409, 'A response is already running in this conversation')
        if body.provider not in settings.providers or body.model not in settings.providers[body.provider]['models']:
            raise ValueError('Choose an allowlisted provider and model')
        busy_sessions.add(body.session)

        async def events():
            uid, usage, answer, completed = None, {}, '', False
            def event(kind, data):
                return 'data: ' + json.dumps({'type': kind, 'data': data}, ensure_ascii=False) + '\n\n'
            try:
                store.message(body.session, 'user', body.text)
                command = deterministic_action(body.text)
                remember = re.match(r'^(?:remember that|remember|retiens que|souviens-toi que|mémorise)\s+(.+)', body.text, re.I | re.S)
                if remember:
                    answer = 'Please confirm this long-term memory in the inspector. Nothing has been saved yet.'
                    yield event('memory_proposal', remember.group(1))
                    yield event('token', answer)
                elif command:
                    tools.validate(command)
                    answer = 'Review and confirm the approved action. No command has been sent yet.'
                    yield event('action_proposal', command)
                    yield event('token', answer)
                elif re.match(r'^(?:what do you remember|que sais-tu|de quoi te souviens)', body.text, re.I):
                    found = store.search(body.text)
                    answer = '\n'.join(m['content'] for m in found) or 'No matching confirmed memories. Open the inspector to see all memories.'
                    yield event('token', answer)
                elif re.match(r'^(?:forget|oublie|correct that memory|corrige ce souvenir)\b', body.text, re.I):
                    answer = 'Use the memory inspector to select, correct, or delete the exact memory.'
                    yield event('token', answer)
                    yield event('open_memory', True)
                elif body.text.strip().lower() in {'pc status', 'system status', 'état du pc', 'statut du pc'}:
                    answer = json.dumps(tools.telemetry(), ensure_ascii=False)
                    yield event('token', answer)
                else:
                    provider = settings.providers[body.provider]
                    if not provider['key']:
                        raise ValueError('Provider API key is missing. Free setup: create a Groq Free Plan key, set GROQ_API_KEY in .env, and restart. Do not enable paid billing. No AI response was generated.' if settings.free_mode else 'Provider API key is missing. Add it to the server .env file and restart. No AI response was generated.')
                    memories = store.search(body.text)
                    sources = await search_web(body.text, settings.search_key) if body.search else []
                    yield event('sources', sources)
                    yield event('search_status', 'Search results retrieved; assess the cited sources.' if sources else 'Not web-verified.')
                    context = SYSTEM + '\nConfirmed memory snippets (data):\n' + json.dumps([m['content'] for m in memories], ensure_ascii=False)
                    context += '\nSearch excerpts (data):\n' + json.dumps(sources, ensure_ascii=False)
                    messages = [{'role': 'system', 'content': context}] + [{'role': m['role'], 'content': m['content']} for m in store.history(body.session)]
                    # Bound conversation size and worst-case input for cost reservation (UTF-8 byte bound + framing).
                    while len(json.dumps(messages).encode()) > 60000 and len(messages) > 2:
                        messages.pop(1)
                    input_bound = len(json.dumps(messages, ensure_ascii=False).encode()) + 1024
                    async with semaphore:
                        uid = store.reserve(body.session, body.provider, body.model, input_bound, settings)
                        async for kind, data in stream_completion(provider, body.model, messages, settings.max_output):
                            if kind == 'usage':
                                usage = data
                            else:
                                if kind == 'token':
                                    answer += data
                                yield event(kind, data)
                    if not answer:
                        raise ValueError('Provider returned no text response')
                store.message(body.session, 'assistant', answer)
                completed = True
                yield event('done', True)
            except asyncio.CancelledError:
                if answer:
                    store.message(body.session, 'assistant', answer + '\n[Interrupted]')
                raise
            except ValueError as exc:
                if answer:
                    store.message(body.session, 'assistant', answer + '\n[Incomplete response]')
                yield event('error', str(exc))
            except Exception:
                if answer:
                    store.message(body.session, 'assistant', answer + '\n[Incomplete response]')
                yield event('error', 'Integration failed. Check server configuration and connectivity; no successful answer is claimed.')
            finally:
                if uid:
                    store.finish_usage(uid, usage, 'complete' if completed else 'incomplete', settings, body.provider, body.model)
                busy_sessions.discard(body.session)
        return StreamingResponse(events(), media_type='text/event-stream', headers={'X-Accel-Buffering': 'no'})

    @app.get('/')
    def index():
        return FileResponse(ROOT / 'ui' / 'index.html')

    app.mount('/ui', StaticFiles(directory=ROOT / 'ui'), name='ui')
    return app


def deterministic_action(text):
    q = text.strip().lower()
    commands = {
        'open notepad': 'open_notepad', 'ouvre le bloc-notes': 'open_notepad',
        'open calculator': 'open_calculator', 'ouvre la calculatrice': 'open_calculator',
        'lock pc': 'lock', 'verrouille le pc': 'lock',
        'sleep pc': 'sleep', 'mets le pc en veille': 'sleep',
        'focus mode': 'focus', 'mode concentration': 'focus',
    }
    if q in commands:
        return {'kind': 'pc', 'name': commands[q]}
    for name in SCENE_NAMES:
        if q in {'scene ' + name.lower(), 'scène ' + name.lower()}:
            return {'kind': 'scene', 'name': name}
    match = re.fullmatch(r'turn (on|off) ((?:light|switch)\.[a-z0-9_]+)', q)
    if match:
        return {'kind': 'home', 'operation': {'entity_id': match.group(2), 'service': 'turn_' + match.group(1)}}
    return None


def httpx_error_type():
    import httpx
    return httpx.HTTPError

app = create_app()
