"""Private, fixed speech worker. Isolates Windows COM from the server."""
import json
import re
import sys


def speak(payload):
    if payload.get('backend') == 'piper':
        from piper import PiperVoice
        import wave
        voice = PiperVoice.load(payload['model'])
        with wave.open(payload['output'], 'wb') as wav:
            voice.synthesize_wav(payload['text'], wav)
        return {'voice': 'Alan · English UK (Piper)', 'backend': 'piper'}
    import pyttsx3
    engine = pyttsx3.init()
    language = payload['language']
    selected = None
    for voice in engine.getProperty('voices'):
        desc = voice.name + ' ' + voice.id
        langs = ' '.join(str(x) for x in getattr(voice, 'languages', []))
        male = ((getattr(voice, 'gender', '') or '').lower() == 'male' or
                re.search(r'\b(?:Paul|Henri|Thomas|David|Mark|Ryan|Daniel|George|James|Male)\b', desc, re.I))
        matching = language in langs.lower() or ('french' in desc.lower() if language == 'fr' else 'english' in desc.lower())
        if male and matching:
            selected = voice
            break
    if selected is None:
        raise RuntimeError('No installed male voice for this language. Add an English male speech voice in Windows Settings > Time & language > Speech.')
    engine.setProperty('voice', selected.id)
    engine.setProperty('rate', 175)
    try:
        engine.say(payload['text'])
        engine.runAndWait()
    finally:
        engine.stop()
    return {'voice': selected.name}


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        print(json.dumps(speak(json.load(sys.stdin))))
    except Exception as exc:
        print(json.dumps({'error': type(exc).__name__ + ': ' + str(exc)}))
        sys.exit(1)
