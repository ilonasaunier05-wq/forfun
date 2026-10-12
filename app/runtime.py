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
        self.wake_stop = threading.Event()
        self.stop = threading.Event()
        self.recording_stop = None
        self.loop = None
        self.audio_tasks = set()
        self.hotkeys = Hotkeys(self.signal_wake, self.signal_stop)
        self.listeners = set()
        self.confirmations = {}
        self.turn_lock = asyncio.Lock()
        self.mic_lock = asyncio.Lock()
        self.voice_task = None
        self.microphone_error = None
        self.native_session = None
        self.speak_replies = True

    def signal_stop(self):
        self.speaker.interrupt()
        self.wake_stop.set()
        if self.recording_stop: self.recording_stop.set()
        if self.loop and not self.loop.is_closed():
            asyncio.run_coroutine_threadsafe(self.stop_listening(), self.loop)

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
            await self.emit('notice', 'Listening now. Speak into your selected microphone.')
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
        await self.emit('state','awaiting_confirmation')
        token = secrets.token_urlsafe(24)
        future = asyncio.get_running_loop().create_future()
        self.confirmations[token] = (future, origin)
        await self.emit('confirmation', {'id': token, 'prompt': prompt, 'origin': origin, 'expires_in': 90})
        voice_stop = threading.Event()
        voice_task = None
        if origin == 'voice':
            voice_task = asyncio.create_task(self.voice_confirmation(prompt, future, voice_stop))
        if origin == 'console':
            await self.soft_say(prompt + ' Type yes or no in the terminal.', full=True)
        try:
            approved=await asyncio.wait_for(future, 90)
            await self.emit('state','running_action' if approved else 'idle')
            return approved
        except asyncio.TimeoutError:
            return False
        finally:
            voice_stop.set()
            if voice_task:
                self.speaker.interrupt()
                try: await voice_task
                except asyncio.CancelledError: pass
            self.confirmations.pop(token, None)
            await self.emit('confirmation_closed', {'id': token})

    async def voice_confirmation(self, prompt, future, stop):
        await self.emit('notice', 'Confirm on screen, or say yes/no when listening. Silence does not approve or decline the action.')
        try:
            if future.done() or stop.is_set(): return
            await self.soft_say(prompt + ' Say yes or no, or confirm on screen.', full=True)
            if future.done() or stop.is_set(): return
            await self.emit('state', 'listening')
            audio = await self.capture_audio(8, 8, stop)
            if future.done() or stop.is_set(): return
            response = await self.brain.transcribe(audio, self.rate_notice)
            await self.emit('transcript', response)
            response = response.lower().strip(' .!?')
            if not future.done():
                if response in {'yes', 'confirm', 'yes confirm', 'oui', 'confirme', 'oui confirme'}:
                    future.set_result(True)
                elif response in {'no', 'cancel', 'non', 'annule'}:
                    future.set_result(False)
                else:
                    await self.emit('notice', 'Confirmation was unclear. Use Confirm or Cancel on screen.')
        except Exception as exc:
            if not future.done():
                await self.emit('notice', 'Voice confirmation unavailable: ' + self.safe_error(exc) + ' Use Confirm or Cancel on screen.')
        finally:
            if not future.done(): await self.emit('state', 'awaiting_confirmation')

    def answer_confirmation(self, token, approved):
        item = self.confirmations.get(token)
        if not item or item[0].done():
            raise ValueError('Confirmation expired or already answered.')
        item[0].set_result(approved)

    async def rate_notice(self, text):
        await self.emit('notice',text)
        await self.soft_say(text)

    async def capture_audio(self, wait_timeout, max_seconds, stop=None):
        stop = stop or threading.Event()
        async with self.mic_lock:
            self.recording_stop = stop
            worker = asyncio.create_task(asyncio.to_thread(self.mic.record, wait_timeout, max_seconds, stop))
            try:
                return await asyncio.shield(worker)
            finally:
                stop.set()
                try: await worker
                except (InterruptedError, TimeoutError, ValueError): pass
                self.recording_stop = None

    async def record_once(self, wait_timeout=10):
        self.wake.clear()
        self.speaker.interrupt()
        await self.emit('state', 'listening')
        audio = await self.capture_audio(wait_timeout, 20)
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
                    if event['type'] == 'assistant_reset': answer = ''
                    if event['type'] == 'token': answer += event['data']
                    if event['type'] == 'rate_limit':
                        await self.soft_say(event['data'])
                    yield event
                self.store.message(sid, 'assistant', answer)
                yield {'type': 'done', 'data': True}
                if speak and self.speak_replies and answer:
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
        self.wake_stop.clear()
        self.voice_task = asyncio.create_task(self._voice_loop())
        await self.emit('notice', 'Microphone calibrated. Double clap or F8 wakes Jarvis. F9 interrupts speech.')

    async def _voice_loop(self):
        import time
        active_until = 0
        try:
            while not self.stop.is_set() and not self.wake_stop.is_set():
                if self.turn_lock.locked() or self.speaker.speaking:
                    await asyncio.sleep(0.1); continue
                if time.monotonic() >= active_until:
                    async with self.mic_lock:
                        await asyncio.to_thread(self.mic.wait_wake, self.wake, self.wake_stop)
                    if self.wake_stop.is_set(): return
                    await self.emit('notice', 'Wake detected. Listening now — speak into your microphone.')
                try:
                    text = await self.record_once(max(1, active_until - time.monotonic()) if active_until > time.monotonic() else 10)
                except TimeoutError as exc:
                    if active_until == 0:
                        await self.emit('error', self.safe_error(exc))
                    await self.emit('state', 'idle')
                    active_until = 0; continue
                except Exception as exc:
                    if not self.mic.stream: raise
                    await self.emit('error',self.safe_error(exc))
                    active_until = 0
                    await asyncio.sleep(1)
                    continue
                await self.native_turn(text, 'voice')
                active_until = time.monotonic() + self.settings.followup_seconds
        except asyncio.CancelledError:
            raise
        except InterruptedError:
            if not self.wake_stop.is_set(): raise
        except Exception as exc:
            self.microphone_error = self.safe_error(exc)
            await self.emit('error', self.microphone_error)

    async def stop_voice(self):
        self.wake_stop.set()
        self.wake.set()
        if self.recording_stop: self.recording_stop.set()
        if self.voice_task:
            self.voice_task.cancel()
            await asyncio.gather(self.voice_task, return_exceptions=True)
            self.voice_task = None

    async def stop_listening(self):
        self.speaker.interrupt()
        if self.recording_stop: self.recording_stop.set()
        for future, origin in list(self.confirmations.values()):
            if origin == 'voice' and not future.done(): future.set_result(False)
        await self.stop_voice()
        tasks = list(self.audio_tasks)
        for task in tasks: task.cancel()
        if tasks: await asyncio.gather(*tasks, return_exceptions=True)
        self.audio_tasks.clear()
        async with self.mic_lock:
            await asyncio.to_thread(self.mic.close)
        await self.emit('state', 'idle')
        await self.emit('notice', 'Microphone stopped. F8 or the microphone button records one request; double clap stays off until enabled.')

    async def close(self):
        self.stop.set(); self.wake_stop.set(); self.wake.set(); self.speaker.interrupt()
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
