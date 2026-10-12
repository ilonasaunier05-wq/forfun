import asyncio
import io
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
import unicodedata
import edge_tts


def sanitize_tts(text):
    text = re.sub(r'\bj[.\s]*a[.\s]*r[.\s]*v[.\s]*i[.\s]*s\.?', 'Jarvis', text, flags=re.I)
    text = re.sub(r'```[\s\S]*?```', 'Code is shown on screen.', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[*#`>_~]', '', text)
    text = ''.join(c for c in text if unicodedata.category(c) not in {'So', 'Cs'} and c not in '\ufe0f\u200d')
    text = re.sub(r'\b[A-ZÀ-Ý]{2,}\b', lambda m: m.group().capitalize(), text)
    return re.sub(r'\s+', ' ', text).strip()


class Speaker:
    def __init__(self, settings, emit):
        self.settings, self.emit = settings, emit
        self.lock = asyncio.Lock()
        self.stop_event = threading.Event()
        self.speaking = False
        self.backend = None
        self.selected_voice = None
        self.engine = None
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="JarvisSAPI")
        self.generation = 0
        self.edge_retry_after = 0.0

    def interrupt(self):
        self.generation += 1
        self.stop_event.set()
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except (ImportError, RuntimeError):
            pass
        # The SAPI worker observes stop_event and calls engine.stop on its own COM thread.

    async def say(self, text, full=False):
        text = sanitize_tts(text)
        if not text:
            return
        if not full and len(text) > 650:
            sentences = re.split(r'(?<=[.!?])\s+', text)
            text = ' '.join(sentences[:2])[:500] + (' La suite est affichée à l’écran.' if self.settings.language == 'fr' else ' The rest is on screen.')
        requested = self.generation
        async with self.lock:
            if requested != self.generation:
                return
            self.stop_event.clear()
            self.speaking = True
            await self.emit('state', 'speaking')
            try:
                audio = io.BytesIO()
                # honor the environment's HTTP proxy; never disable TLS verification
                proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
                async def generate():
                    async for chunk in edge_tts.Communicate(text, self.settings.voice, proxy=proxy).stream():
                        if self.stop_event.is_set():
                            return
                        if chunk['type'] == 'audio':
                            audio.write(chunk['data'])
                try:
                    if time.monotonic() < self.edge_retry_after:
                        raise RuntimeError('Edge voice temporarily unavailable; using Windows voice.')
                    await asyncio.wait_for(generate(), timeout=6)
                    if self.stop_event.is_set():
                        return
                    if not audio.getbuffer().nbytes:
                        raise RuntimeError('Edge TTS returned no audio.')
                    await asyncio.to_thread(self._play, audio.getvalue())
                    self.backend, self.selected_voice = 'edge-tts', self.settings.voice
                except Exception as exc:
                    if self.stop_event.is_set():
                        return
                    self.edge_retry_after = time.monotonic() + 300
                    await self.emit('notice', 'Edge TTS failed (' + type(exc).__name__ + '); trying an installed male system voice.')
                    await asyncio.get_running_loop().run_in_executor(self.worker, self._system_speech, text)
            finally:
                self.speaking = False
                await self.emit('state', 'idle')

    def _play(self, data):
        os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(io.BytesIO(data), 'mp3')
        pygame.mixer.music.play()
        clock = pygame.time.Clock()
        while pygame.mixer.music.get_busy() and not self.stop_event.is_set():
            clock.tick(30)
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()

    def _system_speech(self, text):
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        pattern = r'\b(?:Paul|Henri|Thomas|David|Mark|Ryan|Daniel|George|James|Male)\b'
        language = self.settings.voice.split('-')[0].lower()
        candidates = []
        for voice in voices:
            desc = voice.name + ' ' + voice.id
            langs = ' '.join(str(x) for x in getattr(voice, 'languages', []))
            if ((getattr(voice, 'gender', '') or '').lower() == 'male' or re.search(pattern, desc, re.I)):
                candidates.append((voice, language in langs.lower() or ('french' in desc.lower() if language == 'fr' else 'english' in desc.lower())))
        selected = next((v for v, matching in candidates if matching), None)
        if not selected:
            raise RuntimeError('No installed male voice for the selected language. Add a male speech voice in Windows Settings > Time & language > Speech.')
        self.engine = engine
        engine.setProperty('voice', selected.id)
        engine.setProperty('rate', 175)
        started = False
        try:
            if self.stop_event.is_set(): return
            engine.say(text)
            engine.startLoop(False)
            started = True
            deadline = time.monotonic() + 90
            while engine.isBusy():
                if self.stop_event.is_set():
                    engine.stop()
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError('System TTS playback timeout.')
                engine.iterate()
                time.sleep(0.02)
            self.backend, self.selected_voice = 'pyttsx3', selected.name
        finally:
            engine.stop()
            if started: engine.endLoop()
            self.engine = None

    def close(self):
        self.interrupt()
        self.worker.shutdown(wait=True, cancel_futures=True)
