import asyncio
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.store import Store
from app.tools import Tools
from app.providers import stream_completion, search_web

main = importlib.import_module('app.main')

def settings(directory, **kwargs):
    s = Settings(data_dir=Path(directory), free_mode=False, providers={'openai': {'url': 'https://provider.example/v1', 'key': '', 'models': ['test-model']}} , **kwargs)
    s.rates = {}
    return s

class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = settings(self.tmp.name)
        self.app = create_app(self.settings)
        self.client = TestClient(self.app, base_url='http://localhost', client=('127.0.0.1', 50000))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def sid(self):
        return self.client.post('/api/sessions', json={}).json()['id']

    def chat(self, text, **kwargs):
        return self.client.post('/api/chat', json={'session':self.sid(), 'text':text, 'provider':'openai', 'model':'test-model', **kwargs})

    def test_ui_and_configuration_do_not_expose_keys(self):
        self.settings.providers['openai']['key']='secret-value'
        response=self.client.get('/api/config')
        self.assertNotIn('secret-value', response.text)
        self.assertTrue(response.json()['providers']['openai']['configured'])
        page=self.client.get('/')
        self.assertEqual(page.status_code,200)
        self.assertIn('circle cx="300"',page.text)
        self.assertIn('frame-ancestors',page.headers['content-security-policy'])
        self.assertEqual(self.client.get('/ui/app.js').status_code,200)

    def test_memory_confirmation_search_edit_delete_and_exports(self):
        payload={'content':'I study quantum physics', 'category':'Projects'}
        self.assertEqual(self.client.post('/api/memories',json=payload).status_code,400)
        mid=self.client.post('/api/memories',json={**payload,'confirmed':True}).json()['id']
        results=self.client.get('/api/memories?q=quantum').json()
        self.assertEqual(results[0]['id'],mid)
        markdown=Path(self.tmp.name)/'memory'/'Projects.md'
        self.assertIn('quantum',markdown.read_text())
        self.client.put('/api/memories/'+mid,json={'content':'I study algebra','category':'Projects','confirmed':True})
        self.assertEqual(self.client.get('/api/memories?q=quantum').json(),[])
        self.assertIn('algebra',markdown.read_text())
        self.client.delete('/api/memories/'+mid)
        self.assertNotIn('algebra',markdown.read_text())
        self.assertEqual(self.client.get('/api/memories').json(),[])

    def test_explicit_remember_is_proposal_not_automatic_write(self):
        response=self.chat('Remember that my PIN is 1234')
        self.assertIn('memory_proposal',response.text)
        self.assertEqual(self.client.get('/api/memories').json(),[])
        self.assertEqual(self.client.get('/api/usage').json()['requests'],0)

    def test_missing_key_is_honest_error_and_history_persists(self):
        sid=self.sid()
        response=self.client.post('/api/chat',json={'session':sid,'text':'Hello','provider':'openai','model':'test-model'})
        self.assertIn('API key is missing',response.text)
        self.assertNotIn('"type": "done"',response.text)
        history=self.client.get('/api/sessions/'+sid).json()
        self.assertEqual(len(history),1)
        self.assertEqual(history[0]['role'],'user')
        self.assertEqual(self.client.get('/api/export').json()['messages'][0]['content'],'Hello')
        self.client.delete('/api/sessions/'+sid)
        self.assertEqual(self.client.get('/api/export').json()['messages'],[])

    def test_real_adapter_stream_usage_and_retrieved_memory(self):
        self.settings.providers['openai']['key']='test'
        self.app.state.store.memory('Physics exam on Friday','Projects')
        seen=[]
        async def provider(p, model, messages, maximum):
            seen.extend(messages)
            yield ('token','Hello ')
            yield ('token','world')
            yield ('usage',{'prompt_tokens':12,'completion_tokens':2})
        sid=self.sid()
        with patch.object(main,'stream_completion',provider):
            response=self.client.post('/api/chat',json={'session':sid,'text':'Help with physics','provider':'openai','model':'test-model'})
        self.assertIn('Hello ',response.text)
        self.assertIn('"type": "done"',response.text)
        self.assertIn('Physics exam',seen[0]['content'])
        self.assertEqual(self.client.get('/api/sessions/'+sid).json()[-1]['content'],'Hello world')
        self.assertEqual(self.client.get('/api/usage').json()['output_tokens'],2)

    def test_no_provider_tool_execution_and_search_failure(self):
        self.settings.providers['openai']['key']='test'
        response=self.chat('Current news',search=True)
        self.assertIn('Web search is not configured',response.text)
        self.assertEqual(self.client.get('/api/actions').json(),[])

    def test_action_allowlist_confirmation_replay_dryrun_and_stop(self):
        for action in ({'kind':'pc','name':'powershell'}, {'kind':'pc','name':[]}, {'kind':[]}, {'kind':'home','operation':'bad'}, {'kind':'pc','name':'lock','command':'bad'}, {'kind':'home','operation':{'entity_id':'light.unknown','service':'turn_on'}}):
            self.assertEqual(self.client.post('/api/actions/prepare',json=action).status_code,400)
        prepared=self.client.post('/api/actions/prepare',json={'kind':'pc','name':'lock'}).json()
        result=self.client.post('/api/actions/execute',json={'confirmation':prepared['confirmation']})
        self.assertEqual(result.json()['status'],'dry_run')
        self.assertEqual(self.client.post('/api/actions/execute',json={'confirmation':prepared['confirmation']}).status_code,400)
        prepared=self.client.post('/api/actions/prepare',json={'kind':'pc','name':'sleep'}).json()
        self.client.post('/api/tools',json={'enabled':False})
        self.assertEqual(self.client.post('/api/actions/execute',json={'confirmation':prepared['confirmation']}).status_code,400)
        self.assertEqual(self.client.post('/api/actions/prepare',json={'kind':'pc','name':'lock'}).status_code,400)
        self.assertEqual(len(self.client.get('/api/actions').json()),1)

    def test_deterministic_commands_propose_actions_without_ai_or_execution(self):
        response=self.chat('open calculator')
        self.assertIn('action_proposal',response.text)
        self.assertIn('open_calculator',response.text)
        self.assertEqual(self.client.get('/api/usage').json()['requests'],0)
        self.assertEqual(self.client.get('/api/actions').json(),[])
        response=self.chat('turn off light.unknown')
        self.assertIn('Entity is not allowlisted',response.text)

    def test_emergency_stop_persists_and_scene_change_invalidates_confirmation(self):
        self.client.post('/api/tools',json={'enabled':False})
        self.assertEqual(self.app.state.store.rows("SELECT value FROM settings WHERE key='tools_enabled'")[0]['value'],'false')
        self.client.post('/api/tools',json={'enabled':True})
        scene_file=Path(self.tmp.name)/'scenes.json'
        scene_file.write_text(json.dumps({'Study Mode':{'home':[],'pc':[]}}))
        self.settings.scenes_file=scene_file
        prepared=self.client.post('/api/actions/prepare',json={'kind':'scene','name':'Study Mode'}).json()
        self.assertEqual(prepared['plan'],{'home':[],'pc':[]})
        scene_file.write_text(json.dumps({'Study Mode':{'home':[],'pc':['sleep']}}))
        response=self.client.post('/api/actions/execute',json={'confirmation':prepared['confirmation']})
        self.assertEqual(response.status_code,400)
        self.assertIn('Scene changed',response.text)

    def test_telemetry_and_unconfigured_home(self):
        status=self.client.get('/api/status').json()
        self.assertIn('host_os',status)
        self.assertGreaterEqual(status['memory_percent'],0)
        self.assertEqual(self.client.get('/api/devices').json()['mode'],'demo')

    def test_security_host_origin_and_content_type(self):
        self.assertEqual(self.client.get('/api/config',headers={'host':'evil.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/sessions',json={},headers={'origin':'http://evil.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/sessions',content='{}',headers={'content-type':'text/plain'}).status_code,415)
        self.settings.password='strong password'
        self.assertEqual(self.client.get('/api/config').status_code,401)
        self.assertEqual(self.client.post('/api/login',json={'password':'wrong'}).status_code,401)
        response=self.client.post('/api/login',json={'password':'strong password'})
        self.assertIn('HttpOnly',response.headers['set-cookie'])
        self.assertEqual(self.client.get('/api/config').status_code,200)
        self.client.post('/api/logout',json={})
        self.assertEqual(self.client.get('/api/config').status_code,401)

    def test_request_budget_and_model_allowlist(self):
        self.settings.daily_requests=1
        sid=self.sid()
        store=self.app.state.store
        uid=store.reserve(sid,'openai','test-model',100,self.settings)
        with self.assertRaises(ValueError):store.reserve(sid,'openai','test-model',100,self.settings)
        self.assertEqual(self.chat('hello',model='unknown').status_code,400)
        self.settings.daily_budget=1
        with self.assertRaises(ValueError):store.reserve(sid,'openai','test-model',100,self.settings)

class PersistenceTests(unittest.TestCase):
    def test_restart_and_fts_special_query(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory);sid=store.session();store.message(sid,'user','Persist me');store.memory('C++ projects','Projects');store.db.close()
            store=Store(directory)
            self.assertEqual(store.history(sid)[0]['content'],'Persist me')
            self.assertTrue(store.search('"C++" OR *'))
            store.db.close()

    def test_existing_markdown_is_preserved_without_database(self):
        with tempfile.TemporaryDirectory() as directory:
            memory=Path(directory)/'memory'
            memory.mkdir()
            file=memory/'Profile.md'
            file.write_text('User notes')
            with self.assertRaises(ValueError):Store(directory)
            self.assertEqual(file.read_text(),'User notes')

    def test_budget_reserves_before_payment(self):
        with tempfile.TemporaryDirectory() as directory:
            s=settings(directory,daily_budget=0.001)
            s.rates={'openai/test-model':[1,2]}
            store=Store(directory)
            with self.assertRaises(ValueError):store.reserve(store.session(),'openai','test-model',1000,s)
            self.assertEqual(store.rows('SELECT * FROM usage'),[])
            store.db.close()

class FreeModeTests(unittest.TestCase):
    def test_default_blocks_paid_providers_and_search_even_with_keys(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'JARVIS_FREE_MODE':'true','AI_BASE_URL':'https://api.groq.com/openai/v1','OPENAI_API_KEY':'unused','BRAVE_SEARCH_API_KEY':'unused'}):
            s=Settings(data_dir=Path(directory))
            self.assertEqual(list(s.providers), ['compatible'])
            self.assertEqual(s.search_key, '')
            app=create_app(s)
            with TestClient(app, base_url='http://localhost',client=('127.0.0.1',50000)) as client:
                sid=client.post('/api/sessions',json={}).json()['id']
                cfg=client.get('/api/config').json()
                self.assertTrue(cfg['free_mode'])
                self.assertEqual(cfg['default_provider'],'compatible')
                self.assertFalse(cfg['search_configured'])
                self.assertEqual(client.post('/api/chat',json={'session':sid,'text':'hello','provider':'openai','model':'gpt-4.1-mini'}).status_code,400)
                self.assertEqual(client.post('/api/chat',json={'session':sid,'text':'news','search':True}).status_code,400)
                self.assertEqual(client.get('/api/usage').json()['requests'],0)

    def test_free_mode_rejects_paid_endpoint_override(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'JARVIS_FREE_MODE':'true','AI_BASE_URL':'https://api.openai.com/v1'}):
            with self.assertRaises(ValueError):Settings(data_dir=Path(directory))

class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_protocol_over_http_transport(self):
        requests=[]
        def handler(request):
            requests.append(request)
            return httpx.Response(200,text='data: {"choices":[{"delta":{"content":"Bonjour"}}]}\n\ndata: {"choices":[],"usage":{"prompt_tokens":4,"completion_tokens":1}}\n\ndata: [DONE]\n\n')
        original=httpx.AsyncClient
        with patch('app.providers.httpx.AsyncClient',lambda **kw: original(transport=httpx.MockTransport(handler),**kw)):
            events=[e async for e in stream_completion({'url':'https://example.com/v1','key':'private'},'model',[{'role':'user','content':'hi'}],32)]
        self.assertEqual(events[0],('token','Bonjour'))
        self.assertEqual(events[1][1]['completion_tokens'],1)
        self.assertEqual(requests[0].url.path,'/v1/chat/completions')
        self.assertEqual(json.loads(requests[0].content)['max_tokens'],32)

    async def test_home_allowlist_real_adapter_and_state_filtering(self):
        with tempfile.TemporaryDirectory() as directory:
            s=settings(directory,ha_url='http://ha.local:8123',ha_token='private',ha_entities=['light.desk'],dry_run=False)
            store=Store(directory);tools=Tools(s,store);calls=[]
            def handler(request):
                calls.append(request)
                if request.method=='GET':return httpx.Response(200,json=[{'entity_id':'light.desk','state':'on'}, {'entity_id':'lock.front','state':'unlocked'}])
                return httpx.Response(200,json=[])
            original=httpx.AsyncClient
            with patch('app.tools.httpx.AsyncClient',lambda **kw: original(transport=httpx.MockTransport(handler),**kw)):
                self.assertEqual((await tools.devices())['devices'][0]['entity_id'],'light.desk')
                result=await tools.execute(tools.prepare({'kind':'home','operation':{'entity_id':'light.desk','service':'turn_on','brightness':128}})['confirmation'])
                self.assertEqual(result['status'],'sent')
            self.assertEqual(calls[-1].url.path,'/api/services/light/turn_on')
            with self.assertRaises(ValueError):tools.validate_home({'entity_id':'light.desk','service':'turn_on','rgb_color':[999,0,0]})
            store.db.close()

if __name__=='__main__':unittest.main()
