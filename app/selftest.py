"""Real integration diagnostics. Never substitute fabricated audio, API responses or actions."""
import asyncio
import json
import platform
import threading
from datetime import datetime, timedelta
from .config import Settings
from .runtime import Runtime
from .speech import sanitize_tts
from .tools import ToolRegistry

async def selftest():
    runtime = Runtime()
    results = []
    wav = None
    def report(name, passed, detail):
        detail = runtime.safe_error(detail) if isinstance(detail, Exception) else (f'{len(detail)} real WAV bytes' if isinstance(detail,bytes) else str(detail))
        display=detail
        if isinstance(detail, bytes):display=f'{len(detail)} real WAV bytes'
        print(('PASS' if passed else 'FAIL') + ' | ' + name + ' | ' + str(display)[:1800], flush=True)
        results.append({'check':name,'passed':passed,'detail':detail})
    async def check(name, operation):
        try:
            result = await operation()
            report(name, True, result)
            return result
        except Exception as exc:
            report(name, False, exc)
            return None
    async def consent(prompt):
        print('\n' + prompt, flush=True)
        try: answer = input('Perform this REAL action? Type yes / oui, otherwise no: ').strip().lower()
        except EOFError: answer = ''
        return answer in {'yes','oui'}
    async def real_tool(name, args):
        result = await runtime.tools.call(name,args,consent)
        if result.get('status') in {'cancelled','unavailable'}:
            raise RuntimeError('NOT RUN: ' + result['message'])
        return result
    print('Jarvis real self-test. Changing actions require your explicit confirmation. No audio or device results are fabricated.',flush=True)
    try:
        async def microphone():
            await asyncio.to_thread(runtime.mic.start)
            print('Say: Jarvis, this is a microphone test. Speak now; silence ends the recording.',flush=True)
            audio=await asyncio.to_thread(runtime.mic.record,8,10,runtime.stop)
            if len(audio)<=44:raise RuntimeError('No recorded PCM data.')
            return audio
        wav=await check('microphone recording + silence detection',microphone)
        if isinstance(wav,bytes):
            results[-1]['detail']=f'{len(wav)} WAV bytes recorded from actual input device'
        async def api_and_model():
            client=runtime.brain.api()
            models=await client.models.list()
            if runtime.settings.model not in {m.id for m in models.data}:raise RuntimeError('Configured GROQ_MODEL is not listed for this account.')
            response=await client.chat.completions.create(model=runtime.settings.model,messages=[{'role':'user','content':'Call get_datetime now.'}],tools=[s for s in __import__('app.tools',fromlist=['TOOL_SCHEMAS']).TOOL_SCHEMAS if s['function']['name']=='get_datetime'],tool_choice={'type':'function','function':{'name':'get_datetime'}},max_completion_tokens=512, **({'reasoning_effort':'low'} if runtime.settings.model.startswith('openai/gpt-oss-') else {}))
            calls=response.choices[0].message.tool_calls or []
            if not calls or calls[0].function.name!='get_datetime':raise RuntimeError('Chosen model did not return the required real function call.')
            return {'model':runtime.settings.model,'actual_tool_call':calls[0].function.name}
        await check('Groq authentication + chosen model + function calling',api_and_model)
        async def whisper():
            if not isinstance(wav,bytes):raise RuntimeError('NOT RUN: real microphone recording unavailable.')
            return await runtime.brain.transcribe(wav)
        await check('Whisper real recorded audio transcription',whisper)
        async def tts():
            text=sanitize_tts('J.A.R.V.I.S. — JARVIS. **Hello!** 🤖')
            if 'J.A.R.V.I.S' in text or 'JARVIS' in text or '🤖' in text:raise RuntimeError('TTS sanitizer failed.')
            await asyncio.wait_for(runtime.speaker.say(text,full=True),35)
            if runtime.speaker.backend is None:raise RuntimeError('No playback backend completed.')
            try:heard=input('Did you HEAR a male voice pronounce Jarvis as a word? Type yes/oui: ').strip().lower()
            except EOFError:heard=''
            if heard not in {'yes','oui'}:raise RuntimeError('UNVERIFIED: playback completion does not prove audible pronunciation; human listening confirmation missing.')
            return {'backend':runtime.speaker.backend,'voice':runtime.speaker.selected_voice,'heard_by_user':True}
        await check('male TTS playback + audible Jarvis pronunciation',tts)
        async def claps():
            if not isinstance(wav,bytes):raise RuntimeError('NOT RUN: microphone unavailable.')
            print('Double clap within 10 seconds.',flush=True)
            stop=threading.Event();timer=threading.Timer(10,stop.set);timer.start()
            try:return await asyncio.to_thread(runtime.mic.wait_wake,threading.Event(),stop)
            finally:timer.cancel()
        await check('double-clap wake on real room audio',claps)
        async def hotkeys():
            runtime.hotkeys.start();return 'F8/F9 registered with Windows'
        await check('Windows global hotkey registration',hotkeys)
        await check('get_datetime real local time',lambda:real_tool('get_datetime',{}))
        await check('web_search real DuckDuckGo results',lambda:real_tool('web_search',{'query':'Python official documentation'}))
        await check('list_files actual project directory',lambda:real_tool('list_files',{}))
        async def read():
            files=await runtime.tools.call('list_files',{},consent)
            selected=next((f for f in files['files'] if f.endswith(('.md','.py','.txt'))),None)
            if not selected:raise RuntimeError('NOT RUN: no readable text project file.')
            return await real_tool('read_file',{'path':selected})
        await check('read_file actual project contents',read)
        # Test note/memory writes in a subdirectory of the real NOTES_DIR, not in user profile files.
        original=runtime.tools
        settings=Settings(notes_dir=runtime.settings.notes_dir / ('selftest-'+datetime.now().strftime('%Y%m%d-%H%M%S')))
        isolated=ToolRegistry(settings)
        for name,args in [('add_note',{'text':'Jarvis real self-test note'}),('add_task',{'text':'Jarvis real self-test task'}),('remember',{'fact':'This is a real self-test entry, stored only in the self-test subdirectory.'})]:
            async def write(name=name,args=args):
                result=await isolated.call(name,args,consent)
                if result.get('status')=='cancelled':raise RuntimeError('NOT RUN: action declined or no interactive consent.')
                file=__import__('pathlib').Path(result['path'])
                expected=next(iter(args.values()))
                if expected not in file.read_text(encoding='utf-8'):raise RuntimeError('Written content did not read back correctly.')
                return {'status':'written_and_read_back','path':str(file)}
            await check(name+' real Markdown write/read-back',write)
        await check('open_url real default browser',lambda:real_tool('open_url',{'url':'https://www.python.org'}))
        await check('open_app real allowlisted calculator',lambda:real_tool('open_app',{'name':'calculator'}))
        await check('pc_action real volume key',lambda:real_tool('pc_action',{'name':'volume_up'}))
        start=datetime.now(runtime.settings.tz)+timedelta(minutes=30)
        await check('add_calendar_event real OAuth/create/read-back',lambda:real_tool('add_calendar_event',{'title':'Jarvis self-test (real event)','start':start.isoformat(),'end':(start+timedelta(minutes=10)).isoformat()}))
        async def home():
            if not runtime.settings.ha_entities:raise RuntimeError('NOT RUN: configure HA_URL, HA_TOKEN, HA_ENTITIES first.')
            entity=runtime.settings.ha_entities[0]
            return await real_tool('ha_call_service',{'domain':entity.split('.')[0],'service':'turn_on','entity_id':entity})
        await check('ha_call_service real Home Assistant',home)
    finally:
        path=runtime.tools.confined_write('.private/selftest-report.json')
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({'host':platform.system(),'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
        print('\nResults saved to '+str(path),flush=True)
        await runtime.close()
    passed=sum(r['passed'] for r in results)
    print(f'{passed}/{len(results)} passed. Unavailable/unverified checks remain FAIL with their exact prerequisite.',flush=True)
    return 0 if passed==len(results) else 1
