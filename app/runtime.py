import asyncio
import json
import secrets
import threading
from .config import Settings
from .store import Store
from .tools import ToolRegistry
from .providers import Brain
from .speech import Speaker
from .audio import Microphone, Hotkeys

class Runtime:
    def __init__(self, settings=None):
        self.settings = settings or Settings()
        self.store = Store(self.settings.notes_dir)
        disabled = self.store.rows("SELECT value FROM settings WHERE key='tools_enabled'")
        if disabled: self.settings.tools_enabled = disabled[0]['value'] == 'true'
        self.tools = ToolRegistry(self.settings, self.store)
        self.brain = Brain(self.settings, self.tools)
        self.speaker = Speaker(self.settings, self.emit)
        self.mic = Microphone(self.settings)
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.loop = None
        self.audio_tasks = set()
        self.hotkeys = Hotkeys(self.signal_wake, self.speaker.interrupt)
        self.listeners = set()
        self.confirmations = {}
        self.turn_lock = asyncio.Lock()
        self.mic_lock = asyncio.Lock()
        self.voice_task = None
        self.microphone_error = None
        self.native_session = None
        self.speak_replies = True

    def signal_wake(self):
        self.speaker.interrupt()
        self.wake.set()
        if self.stop.is_set() or not self.loop or self.loop.is_closed(): return
        if self.voice_task and not self.voice_task.done(): return
        def launch():
            if self.audio_tasks or self.stop.is_set(): return
            task=asyncio.create_task(self.hotkey_turn())
            self.audio_tasks.add(task);task.add_done_callback(self.audio_tasks.discard)
        self.loop.call_soon_threadsafe(launch)

    async def hotkey_turn(self):
        try:
            await asyncio.sleep(0.15)
            if self.turn_lock.locked():
                await self.emit('notice','A response or confirmation is still active; finish it before a new voice turn.')
                return
            await self.soft_say('Yes?')
            text=await self.record_once()
            await self.native_turn(text,'voice')
        except Exception as exc:
            await self.emit('error',self.safe_error(exc))

    def safe_error(self, exc):
        message = str(exc)
        for key in (self.settings.key, self.settings.ha_token):
            if key: message = message.replace(key, '[redacted]')
        return type(exc).__name__ + ': ' + message

    async def emit(self, kind, data):
        encoded = json.dumps({'type': kind, 'data': data}, ensure_ascii=False)
        for secret in (self.settings.key, self.settings.ha_token):
            if secret: encoded = encoded.replace(secret, '[redacted]')
        event = json.loads(encoded)
        for listener in list(self.listeners):
            try: listener.put_nowait(event)
            except asyncio.QueueFull:
                self.listeners.discard(listener)
        if kind in {'transcript', 'error', 'notice', 'confirmation', 'tool_call', 'tool_result'}:
            message = json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data
            for key in (self.settings.key, self.settings.ha_token):
                if key: message = message.replace(key, '[redacted]')
            print(kind + ': ' + message, flush=True)

    async def soft_say(self, text, full=False):
        try:
            await self.speaker.say(text, full=full)
        except Exception as exc:
            await self.emit('error', self.safe_error(exc))

    async def confirm(self, prompt, origin):
        if origin == 'voice':
            await self.emit('notice',prompt)
            await self.soft_say(prompt + (' Dis oui pour confirmer.' if self.settings.language == 'fr' else ' Say yes to confirm.'), full=True)
            async with self.mic_lock:
                audio = await asyncio.to_thread(self.mic.record, 8, 8, self.stop)
                response = await self.brain.transcribe(audio, self.rate_notice)
            await self.emit('transcript', response)
            return response.lower().strip(' .!?') in {'yes', 'confirm', 'yes confirm', 'oui', 'confirme', 'oui confirme'}
        await self.emit('state','awaiting_confirmation')
        token = secrets.token_urlsafe(24)
        future = asyncio.get_running_loop().create_future()
        self.confirmations[token] = (future, origin)
        await self.emit('confirmation', {'id': token, 'prompt': prompt, 'origin': origin, 'expires_in': 90})
        if origin == 'console':
            await self.soft_say(prompt + ' Type yes or no in the terminal.', full=True)
        try:
            approved=await asyncio.wait_for(future, 90)
            await self.emit('state','running_action' if approved else 'idle')
            return approved
        except asyncio.TimeoutError:
            return False
        finally:
            self.confirmations.pop(token, None)

    def answer_confirmation(self, token, approved):
        item = self.confirmations.get(token)
        if not item or item[0].done():
            raise ValueError('Confirmation expired or already answered.')
        item[0].set_result(approved)

    async def rate_notice(self, text):
        await self.emit('notice',text)
        await self.soft_say(text)

    async def record_once(self, wait_timeout=10):
        self.wake.clear()
        self.speaker.interrupt()
        async with self.mic_lock:
            await self.emit('state', 'listening')
            audio = await asyncio.to_thread(self.mic.record, wait_timeout, 20, self.stop)
            self.microphone_error = None
            await self.emit('state', 'transcribing')
            text = await self.brain.transcribe(audio, self.rate_notice)
        await self.emit('transcript', text)
        return text

    async def chat(self, sid, text, origin='ui', speak=True, model=None):
        if any(secret and secret in text for secret in (self.settings.key,self.settings.ha_token)):
            raise ValueError('Keep credentials in .env, not in conversation messages.')
        if self.turn_lock.locked():
            raise RuntimeError('A turn is active. Finish its confirmation or interrupt first.')
        async with self.turn_lock:
            self.store.message(sid, 'user', text)
            await self.emit('state', 'thinking')
            answer = ''
            try:
                async for event in self.brain.reply(self.store.history(sid), lambda prompt: self.confirm(prompt, origin), model):
                    if event['type'] == 'token': answer += event['data']
                    if event['type'] == 'rate_limit':
                        await self.soft_say(event['data'])
                    yield event
                self.store.message(sid, 'assistant', answer)
                yield {'type': 'done', 'data': True}
                if speak and answer:
                    await self.soft_say(answer)
            except asyncio.CancelledError:
                self.speaker.interrupt()
                if answer: self.store.message(sid, 'assistant', answer + '\n[Interrupted]')
                raise
            except Exception as exc:
                if answer: self.store.message(sid, 'assistant', answer + '\n[Incomplete]')
                yield {'type': 'error', 'data': self.safe_error(exc)}
            finally:
                await self.emit('state', 'idle')

    async def native_turn(self, text, origin):
        if not self.native_session:
            self.native_session = self.store.session()
        await self.emit('native_user', {'session': self.native_session, 'text': text})
        async for event in self.chat(self.native_session, text, origin):
            await self.emit(event['type'], event['data'])
            if event['type'] == 'token': print(event['data'], end='', flush=True)
        print()

    async def start_voice(self):
        if self.voice_task and not self.voice_task.done():
            return
        self.loop=asyncio.get_running_loop()
        await asyncio.to_thread(self.mic.start)
        self.microphone_error = None
        self.voice_task = asyncio.create_task(self._voice_loop())
        await self.emit('notice', 'Microphone calibrated. Double clap or F8 wakes Jarvis. F9 interrupts speech.')

    async def _voice_loop(self):
        import time
        active_until = 0
        try:
            while not self.stop.is_set():
                if self.turn_lock.locked() or self.speaker.speaking:
                    await asyncio.sleep(0.1); continue
                if time.monotonic() >= active_until:
                    async with self.mic_lock:
                        await asyncio.to_thread(self.mic.wait_wake, self.wake, self.stop)
                    await self.soft_say('Yes?')
                try:
                    text = await self.record_once(max(1, active_until - time.monotonic()) if active_until > time.monotonic() else 10)
                except TimeoutError:
                    active_until = 0; continue
                except Exception as exc:
                    if not self.mic.stream: raise
                    await self.emit('error',self.safe_error(exc))
                    active_until = 0
                    await asyncio.sleep(1)
                    continue
                await self.native_turn(text, 'voice')
                active_until = time.monotonic() + 30
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.microphone_error = self.safe_error(exc)
            await self.emit('error', self.microphone_error)

    async def close(self):
        self.stop.set(); self.wake.set(); self.speaker.interrupt()
        for future, _ in self.confirmations.values():
            if not future.done(): future.set_result(False)
        for task in self.audio_tasks: task.cancel()
        if self.audio_tasks: await asyncio.gather(*self.audio_tasks,return_exceptions=True)
        if self.voice_task:
            self.voice_task.cancel()
            try: await self.voice_task
            except asyncio.CancelledError: pass
        await asyncio.to_thread(self.mic.close)
        self.hotkeys.close()
        await asyncio.to_thread(self.speaker.close)
        await self.brain.close()
        self.store.db.close()
