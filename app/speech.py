import asyncio
import io
import os
import re
import threading
import time
import json
import subprocess
import sys
from pathlib import Path
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
        self.process = None
        self.system_retry_after = 0.0
        self.last_error = None
        self.generation = 0
        self.edge_retry_after = 0.0

    def interrupt(self):
        self.generation += 1
        self.stop_event.set()
        # The playback worker observes stop_event; never call audio drivers on the UI/server thread.
        if self.process is not None and self.process.poll() is None:
            try: self.process.kill()
            except OSError: pass

    async def say(self, text, full=False):
        if time.monotonic() < self.edge_retry_after and time.monotonic() < self.system_retry_after:
            return  # The first failure is visible in HUD status; do not repeat it every turn.
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
                    await self._system_speech(text)
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

    async def _system_speech(self, text):
        if time.monotonic() < self.system_retry_after:
            raise RuntimeError('Windows voice is unavailable. Conversation remains active; check Windows speech voices and audio output, then restart Jarvis.')
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name('system_voice.py'))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', creationflags=flags,
        )
        self.process = process
        try:
            process.stdin.write(json.dumps({'text': text, 'language': self.settings.voice.split('-')[0].lower()}))
            process.stdin.close()
            # A blocked COM driver must never retain the conversation lock indefinitely.
            deadline = time.monotonic() + min(45, max(15, len(text.split()) / 2 + 8))
            while process.poll() is None:
                if self.stop_event.is_set():
                    process.kill()
                    return
                if time.monotonic() >= deadline:
                    raise TimeoutError('Windows speech stopped responding. Voice disabled for five minutes; text and microphone remain available.')
                await asyncio.sleep(0.05)
            if self.stop_event.is_set(): return
            output = process.stdout.read()
            if process.returncode != 0:
                try: detail = json.loads(output).get('error', 'Windows speech failed.')
                except (ValueError, TypeError): detail = 'Windows speech process failed.'
                raise RuntimeError(detail)
            result = json.loads(output)
            self.backend, self.selected_voice = 'pyttsx3', result['voice']
            self.last_error = None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = str(exc)
            self.system_retry_after = time.monotonic() + 300
            raise
        finally:
            if process.poll() is None: process.kill()
            await asyncio.to_thread(process.wait, 3)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None and not pipe.closed: pipe.close()
            self.process = None

    def close(self):
        self.interrupt()
