"""Install the fixed English male Piper voice with upstream integrity checks."""
import hashlib
import json
from pathlib import Path
import httpx

VOICE = 'en_GB-alan-medium'
BASE = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/'


def setup_voice(settings):
    directory = (settings.private_dir / 'voices').resolve()
    if not directory.is_relative_to(settings.notes_dir):
        raise ValueError('Voice directory escapes NOTES_DIR.')
    directory.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        response = client.get(BASE + 'voices.json')
        response.raise_for_status()
        metadata = response.json()[VOICE]
        for suffix in ('.onnx', '.onnx.json'):
            relative = f'en/en_GB/alan/medium/{VOICE}{suffix}'
            expected = metadata['files'][relative]
            target = directory / (VOICE + suffix)
            def valid():
                if not target.exists() or target.stat().st_size != expected['size_bytes']: return False
                digest = hashlib.md5(usedforsecurity=False)
                with target.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(65536), b''): digest.update(chunk)
                return digest.hexdigest() == expected['md5_digest']
            if valid(): continue
            partial = target.with_name(target.name + '.part')
            digest = hashlib.md5(usedforsecurity=False)
            try:
                print('Downloading English male voice:', target.name, flush=True)
                with client.stream('GET', BASE + relative) as response:
                    response.raise_for_status()
                    with partial.open('wb') as stream:
                        size = 0
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > expected['size_bytes']: raise ValueError('Voice download exceeds upstream size.')
                            digest.update(chunk);stream.write(chunk)
                if size != expected['size_bytes'] or digest.hexdigest() != expected['md5_digest']:
                    raise ValueError('Voice download integrity check failed.')
                partial.replace(target)
            finally:
                partial.unlink(missing_ok=True)
    # Check that the real inference engine can load the actual downloaded model.
    from piper import PiperVoice
    import io, wave
    voice = PiperVoice.load(str(directory / (VOICE + '.onnx')))
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as wav: voice.synthesize_wav('Jarvis at your service.', wav)
    if len(audio.getvalue()) <= 44: raise RuntimeError('Piper generated no audio.')
    print('English male voice installed; real speech WAV generated. Run Voice Test to verify your speakers.', flush=True)
