"""Local tests use real temporary files and registry execution. No external service is fabricated."""
import asyncio
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from fastapi.testclient import TestClient
from app.config import Settings
from app.runtime import Runtime
from app.main import create_app
from app.tools import ToolRegistry
from app.speech import sanitize_tts

async def approve(prompt):return True
async def decline(prompt):return False

class RealToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.settings=Settings(notes_dir=self.root/'notes',projects_dir=self.root/'projects',key='')
        self.settings.projects_dir.mkdir()
        self.tools=ToolRegistry(self.settings)
    def tearDown(self):self.temp.cleanup()

    async def test_real_note_task_memory_write_and_readback(self):
        for name,args,file in [('add_note',{'text':'Real note'},'Notes.md'),('add_task',{'text':'Study algebra'},'Tasks.md'),('remember',{'fact':'My class is algebra'},'memory.md')]:
            result=await self.tools.call(name,args,approve)
            self.assertEqual(result['status'],'saved')
            self.assertIn(next(iter(args.values())),(self.settings.notes_dir/file).read_text())
            self.assertTrue(Path(result['path']).is_relative_to(self.settings.notes_dir))

    async def test_declined_action_never_writes(self):
        result=await self.tools.call('add_note',{'text':'Not approved'},decline)
        self.assertEqual(result['status'],'cancelled')
        self.assertFalse((self.settings.notes_dir/'Notes.md').exists())

    async def test_real_read_file_numbering_and_truncation(self):
        file=self.settings.projects_dir/'code.py';file.write_text('\n'.join('print('+str(i)+')' for i in range(2000)))
        result=await self.tools.call('read_file',{'path':'code.py'},approve)
        self.assertIn('42: print(41)',result['text'])
        self.assertTrue(result['truncated'])
        self.assertLessEqual(len(result['text']),16000)
        self.assertIn('code.py',(await self.tools.call('list_files',{},approve))['files'])
        self.settings.key='private'+'credential'
        file.write_text(self.settings.key)
        self.assertNotIn(self.settings.key,(await self.tools.call('read_file',{'path':'code.py'},approve))['text'])

    async def test_traversal_symlink_and_secret_protection(self):
        outside=self.root/'outside.txt';outside.write_text('Private')
        for path in ['../outside.txt',str(outside)]:
            with self.assertRaises(ValueError):await self.tools.call('read_file',{'path':path},approve)
        for filename in ['jarvis.sqlite3-wal','jarvis.sqlite3-shm','credentials.json']:
            hidden=self.settings.projects_dir/filename;hidden.write_text('private')
            with self.assertRaises(ValueError):await self.tools.call('read_file',{'path':filename},approve)
        secret=self.settings.projects_dir/'.env';secret.write_text('GROQ_API_KEY=do-not-read')
        with self.assertRaises(ValueError):await self.tools.call('read_file',{'path':'.env'},approve)
        self.assertNotIn('.env',(await self.tools.call('list_files',{},approve))['files'])
        link=self.settings.projects_dir/'escape.txt'
        try:link.symlink_to(outside)
        except OSError:return  # Windows needs link privilege; traversal checks already executed.
        with self.assertRaises(ValueError):await self.tools.call('read_file',{'path':'escape.txt'},approve)
        self.settings.notes_dir.mkdir(exist_ok=True)
        (self.settings.notes_dir/'Notes.md').symlink_to(outside)
        with self.assertRaises(ValueError):await self.tools.call('add_note',{'text':'Escape'},approve)
        self.assertEqual(outside.read_text(),'Private')

    async def test_real_time_and_relative_dates(self):
        now=await self.tools.call('get_datetime',{},approve)
        self.assertLess(abs((datetime.fromisoformat(now['datetime'])-datetime.now(self.settings.tz)).total_seconds()),3)
        event=self.tools.resolve_event({'title':'Study','start':'Friday at 3pm','end':'Friday at 4pm'})
        start=datetime.fromisoformat(event['start']['dateTime']);end=datetime.fromisoformat(event['end']['dateTime'])
        self.assertEqual(start.weekday(),4);self.assertEqual(start.hour,15);self.assertEqual(end.hour,16)
        self.assertGreater(end,start)

    async def test_allowlist_rejects_shell_and_invalid_urls(self):
        for name,args in [('shell',{'command':'dir'}),('open_app',{'name':'powershell'}),('open_url',{'url':'file:///C:/Windows'}),('open_url',{'url':'https://user:password@example.com'}),('ha_call_service',{'domain':'lock','service':'unlock','entity_id':'lock.door'})]:
            with self.assertRaises(ValueError):self.tools.validate(name,args)

    async def test_optional_integrations_are_unavailable_not_success(self):
        self.settings.ha_entities=['light.desk']
        result=await self.tools.call('ha_call_service',{'domain':'light','service':'turn_on','entity_id':'light.desk'},approve)
        self.assertEqual(result['status'],'unavailable')
        self.settings.credentials_file=self.root/'absent.json'
        result=await self.tools.call('add_calendar_event',{'title':'Study','start':'tomorrow 3pm','end':'tomorrow 4pm'},approve)
        self.assertEqual(result['status'],'unavailable')

    async def test_emergency_stop_blocks_real_writes(self):
        self.settings.tools_enabled=False
        with self.assertRaises(ValueError):await self.tools.call('add_task',{'text':'Blocked'},approve)
        self.assertFalse((self.settings.notes_dir/'Tasks.md').exists())

class VoiceTextTests(unittest.TestCase):
    def test_sanitizer_name_markdown_code_emoji_and_caps(self):
        text=sanitize_tts('J.A.R.V.I.S. JARVIS jarvis **READY** 🤖 ```python\nprint(42)\n``` [source](https://example.com)')
        self.assertEqual(text.count('Jarvis'),3)
        self.assertIn('Ready',text)
        for bad in ['J.A.R.V.I.S','JARVIS','READY','🤖','print(42)','**','https://']:self.assertNotIn(bad,text)

class VoiceConfirmationTests(unittest.IsolatedAsyncioTestCase):
    async def test_voice_action_can_be_confirmed_on_screen_without_tts_or_mic(self):
        for approved in (True, False):
            with tempfile.TemporaryDirectory() as directory:
                runtime = Runtime(Settings(notes_dir=Path(directory), projects_dir=Path(directory), key=''))
                events = asyncio.Queue()
                runtime.listeners.add(events)
                task = asyncio.create_task(runtime.confirm('Confirm add_note?', 'voice'))
                while True:
                    event = await events.get()
                    if event['type'] == 'confirmation':
                        self.assertEqual(event['data']['origin'], 'voice')
                        runtime.answer_confirmation(event['data']['id'], approved)
                        break
                self.assertEqual(await asyncio.wait_for(task, 2), approved)
                self.assertFalse(runtime.confirmations)
                await runtime.close()

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        settings=Settings(notes_dir=Path(self.temp.name)/'notes',projects_dir=Path(self.temp.name),key='')
        self.runtime=Runtime(settings)
        self.client=TestClient(create_app(self.runtime),base_url='http://localhost',client=('127.0.0.1',50000));self.client.__enter__()
    def tearDown(self):self.client.__exit__(None,None,None);self.temp.cleanup()
    def test_hud_kept_and_native_configuration(self):
        page=self.client.get('/');self.assertEqual(page.status_code,200);self.assertIn('circle cx="300"',page.text)
        self.assertIn('frame-ancestors',page.headers['content-security-policy'])
        cfg=self.client.get('/api/config').json();self.assertEqual(cfg['voice'],'en-GB-RyanNeural');self.assertIn('web_search',cfg['tools']);self.assertNotIn('key',cfg)
    def test_stop_disables_listening_without_stopping_server(self):
        result = self.client.post('/api/voice/stop',json={})
        self.assertEqual(result.status_code,200)
        self.assertFalse(result.json()['listening'])
        self.assertTrue(self.runtime.wake_stop.is_set())
        self.assertFalse(self.client.get('/api/status').json()['voice_active'])
        self.assertEqual(self.client.get('/api/config').status_code,200)

    def test_actual_missing_key_error_no_fake_reply(self):
        sid=self.client.post('/api/sessions',json={}).json()['id']
        response=self.client.post('/api/chat',json={'session':sid,'text':'Hello','speak':False})
        self.assertIn('GROQ_API_KEY is missing',response.text);self.assertNotIn('"type": "done"',response.text)
        self.assertEqual(self.client.get('/api/sessions/'+sid).json()[0]['content'],'Hello')
    def test_host_origin_and_auth(self):
        self.assertEqual(self.client.get('/api/config',headers={'host':'evil.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/sessions',json={},headers={'origin':'http://evil.example'}).status_code,403)
        self.runtime.settings.password='private-password'
        self.assertEqual(self.client.get('/api/config').status_code,401)
        self.assertEqual(self.client.post('/api/login',json={'password':'private-password'}).status_code,200)
        self.assertEqual(self.client.get('/api/config').status_code,200)
    def test_confirmed_legacy_memory_persistence(self):
        payload={'content':'Study physics','category':'Projects'}
        self.assertEqual(self.client.post('/api/memories',json=payload).status_code,400)
        mid=self.client.post('/api/memories',json={**payload,'confirmed':True}).json()['id']
        self.assertIn('Study physics',(self.runtime.settings.notes_dir/'memory'/'Projects.md').read_text())
        self.assertEqual(self.client.delete('/api/memories/'+mid).status_code,400)
        self.assertEqual(self.client.delete('/api/memories/'+mid,headers={'X-Jarvis-Confirm':'yes'}).status_code,200)

if __name__=='__main__':unittest.main()
