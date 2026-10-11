import io
import queue
import threading
import time
import wave
from collections import deque
import numpy as np

class Microphone:
    def __init__(self, settings):
        self.settings = settings
        self.sample_rate = 16000
        self.queue = queue.Queue(maxsize=300)
        self.stream = None
        self.noise = 0.003
        self.last_level = 0.0
        self.lock = threading.Lock()

    def start(self):
        if self.stream:
            return
        import sounddevice as sd
        device = self.settings.input_device or None
        if isinstance(device, str) and device.isdigit():
            device = int(device)
        def callback(data, frames, timing, status):
            chunk = data[:, 0].copy()
            self.last_level = float(np.sqrt(np.mean(chunk * chunk)))
            try:
                self.queue.put_nowait(chunk)
            except queue.Full:
                try: self.queue.get_nowait()
                except queue.Empty: pass
                try: self.queue.put_nowait(chunk)
                except queue.Full: pass
        self.sample_rate = int(sd.query_devices(device, 'input')['default_samplerate'])
        try:
            self.stream = sd.InputStream(samplerate=self.sample_rate, blocksize=int(self.sample_rate * 0.02), channels=1, dtype='float32', callback=callback, device=device)
            self.stream.start()
            samples = [self.rms(self.queue.get(timeout=2)) for _ in range(50)]
            self.noise = max(float(np.median(samples)), 0.001)
        except Exception:
            if self.stream:
                self.stream.close()
            self.stream = None
            raise

    @staticmethod
    def rms(chunk):
        return float(np.sqrt(np.mean(chunk * chunk)))

    def flush(self):
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                return

    def wait_wake(self, wake_event, stop_event):
        threshold = max(self.noise * self.settings.clap_sensitivity, 0.025)
        first, previous_high, high_since = None, False, 0
        while not stop_event.is_set():
            if wake_event.is_set():
                wake_event.clear()
                return 'hotkey'
            try:
                chunk = self.queue.get(timeout=0.1)
            except queue.Empty:
                continue
            t, high = time.monotonic(), self.rms(chunk) > threshold
            if high and not previous_high:
                high_since = t
            if previous_high and not high and t - high_since < 0.15:
                if first is not None and 0.12 <= t - first <= 0.7:
                    return 'double_clap'
                first = t
            if first is not None and t - first > 0.7:
                first = None
            previous_high = high
        raise InterruptedError('Microphone stopped.')

    def record(self, wait_timeout=10, max_seconds=20, stop_event=None):
        stop_event = stop_event or threading.Event()
        with self.lock:
            self.start()
            self.flush()
            pre = deque(maxlen=15)
            chunks, started, silent = [], False, 0.0
            deadline = time.monotonic() + wait_timeout
            duration = 0.0
            threshold = max(self.noise * 2.5, 0.008)
            while not stop_event.is_set():
                if not started and time.monotonic() > deadline:
                    raise TimeoutError('No speech detected. Check microphone selection/permissions, or use typed text.')
                try:
                    chunk = self.queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                level = self.rms(chunk)
                if not started:
                    pre.append(chunk)
                    if level >= threshold:
                        started = True
                        chunks.extend(pre)
                    continue
                chunks.append(chunk)
                duration += len(chunk) / self.sample_rate
                silent = silent + len(chunk) / self.sample_rate if level < threshold else 0
                if silent >= self.settings.silence_seconds or duration >= max_seconds:
                    break
            if stop_event.is_set():
                raise InterruptedError('Recording interrupted.')
            data = np.concatenate(chunks)
            pcm = (np.clip(data, -1, 1) * 32767).astype('<i2').tobytes()
            out = io.BytesIO()
            with wave.open(out, 'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(self.sample_rate); wav.writeframes(pcm)
            return out.getvalue()

    def close(self):
        if self.stream:
            self.stream.stop(); self.stream.close(); self.stream = None

class Hotkeys:
    def __init__(self, wake, interrupt):
        self.wake, self.interrupt = wake, interrupt
        self.thread_id = None
        self.ready = threading.Event()
        self.error = None

    def start(self):
        import platform
        if platform.system() != 'Windows':
            raise RuntimeError('Global F8/F9 hotkeys require Windows; HUD/text controls remain available.')
        threading.Thread(target=self._loop, daemon=True).start()
        self.ready.wait(3)
        if self.error:
            raise RuntimeError(self.error)
        if not self.ready.is_set():
            raise RuntimeError('Hotkey registration timed out.')

    def _loop(self):
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        self.thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, 1, 0x4000, 0x77):
            self.error = 'F8 is already registered by another application.'
        elif not user32.RegisterHotKey(None, 2, 0x4000, 0x78):
            self.error = 'F9 is already registered by another application.'
        self.ready.set()
        try:
            if self.error:
                return
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:
                    self.wake() if msg.wParam == 1 else self.interrupt()
        finally:
            user32.UnregisterHotKey(None, 1); user32.UnregisterHotKey(None, 2)

    def close(self):
        if self.thread_id:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
