import ctypes
import json
import platform
import secrets
import subprocess
import time
import httpx
import psutil

PC_ACTIONS = {'open_notepad', 'open_calculator', 'focus', 'lock', 'sleep'}
SCENE_NAMES = ('Dark Feminine', 'Study Mode', 'Gaming Mode', 'Welcome Home', 'Good Night')

class Tools:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store
        self.pending = {}

    def scenes(self):
        scenes = {name: {'home': [], 'pc': []} for name in SCENE_NAMES}
        if self.settings.scenes_file.exists():
            configured = json.loads(self.settings.scenes_file.read_text(encoding='utf-8'))
            if not isinstance(configured, dict) or set(configured) - set(SCENE_NAMES):
                raise ValueError('scenes.json must map the five approved scene names to operation lists')
            scenes.update(configured)
        return scenes

    def validate_home(self, op):
        if not isinstance(op, dict):
            raise ValueError('Home operation must be an object')
        if set(op) - {'entity_id', 'service', 'brightness', 'rgb_color'}:
            raise ValueError('Unsupported home arguments')
        entity, service = op.get('entity_id', ''), op.get('service', '')
        if not isinstance(entity, str) or not isinstance(service, str):
            raise ValueError('Entity and service must be strings')
        domain = entity.split('.')[0]
        if entity not in self.settings.ha_entities or domain not in {'light', 'switch', 'scene'}:
            raise ValueError('Entity is not allowlisted')
        if service not in ({'turn_on'} if domain == 'scene' else {'turn_on', 'turn_off'}):
            raise ValueError('Service is not allowlisted')
        if ('brightness' in op or 'rgb_color' in op) and (domain != 'light' or service != 'turn_on'):
            raise ValueError('Color and brightness apply only to light.turn_on')
        if 'brightness' in op and (type(op['brightness']) is not int or not 0 <= op['brightness'] <= 255):
            raise ValueError('Brightness must be 0–255')
        if 'rgb_color' in op and (not isinstance(op['rgb_color'], list) or len(op['rgb_color']) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in op['rgb_color'])):
            raise ValueError('RGB must contain three integers from 0–255')

    def validate(self, action):
        if not isinstance(action, dict):
            raise ValueError('Action must be an object')
        if not self.settings.tools_enabled:
            raise ValueError('Tools are disabled by emergency stop')
        if not isinstance(action.get('kind'), str):
            raise ValueError('Action kind must be a string')
        if action.get('kind') in {'pc', 'scene'} and not isinstance(action.get('name'), str):
            raise ValueError('Action name must be a string')
        if action.get('kind') == 'pc' and set(action) == {'kind', 'name'} and action['name'] in PC_ACTIONS:
            return
        if action.get('kind') == 'home' and set(action) == {'kind', 'operation'}:
            self.validate_home(action['operation'])
            return
        if action.get('kind') == 'scene' and set(action) == {'kind', 'name'} and action['name'] in SCENE_NAMES:
            scene = self.scenes().get(action['name'], {})
            if not isinstance(scene, dict) or not isinstance(scene.get('home', []), list) or not isinstance(scene.get('pc', []), list):
                raise ValueError('Scene must contain lists of home and PC operations')
            if set(scene) - {'home', 'pc'}:
                raise ValueError('Invalid scene fields')
            for op in scene.get('home', []):
                self.validate_home(op)
            for pc in scene.get('pc', []):
                self.validate({'kind': 'pc', 'name': pc})
            return
        raise ValueError('Action is not allowlisted')

    def prepare(self, action):
        self.validate(action)
        self.pending = {k: v for k, v in self.pending.items() if v[0] > time.monotonic()}
        if len(self.pending) >= 100:
            raise ValueError('Too many pending confirmations')
        nonce = secrets.token_urlsafe(32)
        # Store the validated payload; the confirmation cannot substitute arguments.
        plan = self.scenes()[action['name']] if action['kind'] == 'scene' else action
        self.pending[nonce] = (time.monotonic() + 60, json.loads(json.dumps(action)), json.loads(json.dumps(plan)))
        return {'confirmation': nonce, 'action': action, 'plan': plan, 'dry_run': self.settings.dry_run, 'expires_in': 60}

    async def execute(self, nonce):
        item = self.pending.pop(nonce, None)
        if not item or item[0] < time.monotonic():
            raise ValueError('Confirmation expired or already used; prepare again')
        action = item[1]
        self.validate(action)
        if action['kind'] == 'scene' and self.scenes().get(action['name']) != item[2]:
            raise ValueError('Scene changed after confirmation; review again')
        try:
            result = await self.run(action)
        except Exception as exc:
            self.store.log_action(action, {'status': 'failed', 'error': str(exc)})
            raise
        self.store.log_action(action, result)
        return result

    async def run(self, action):
        if self.settings.dry_run:
            return {'status': 'dry_run', 'message': 'DEMO / DRY RUN: validated only. No PC or home command was sent.', 'action': action}
        if action['kind'] == 'pc':
            return self.pc(action['name'])
        if action['kind'] == 'home':
            return await self.home(action['operation'])
        scene = self.scenes().get(action['name'], {})
        if not scene.get('home') and not scene.get('pc'):
            return {'status': 'demo', 'message': 'DEMO scene: no devices or PC actions are configured.'}
        # Preflight all operations before changing anything. Hardware calls are not atomic.
        if scene.get('pc') and platform.system() != 'Windows':
            raise ValueError('This scene requires the Windows host')
        if scene.get('home') and not (self.settings.ha_url and self.settings.ha_token):
            raise ValueError('Home Assistant is not configured')
        results = []
        try:
            for op in scene.get('home', []):
                results.append(await self.home(op))
            for name in scene.get('pc', []):
                results.append(self.pc(name))
        except Exception:
            return {'status': 'partial_failure', 'completed': results, 'message': 'Scene stopped after a failure. Earlier operations may have completed; no rollback is promised.'}
        return {'status': 'sent', 'message': 'Configured scene commands sent; check device state.', 'results': results}

    def pc(self, name):
        if platform.system() != 'Windows':
            raise ValueError('PC actions require the Windows host. Cloud/Linux telemetry is not your Windows PC.')
        if name == 'open_notepad':
            subprocess.Popen(['notepad.exe'])
        elif name == 'open_calculator':
            subprocess.Popen(['calc.exe'])
        elif name == 'focus':
            subprocess.Popen(['notepad.exe'])  # Intentionally modest approved focus workflow.
        elif name == 'lock':
            if not ctypes.windll.user32.LockWorkStation():
                raise ValueError('Windows refused to lock the workstation')
        elif name == 'sleep':
            if not ctypes.windll.powrprof.SetSuspendState(False, False, False):
                raise ValueError('Windows refused the sleep request')
        return {'status': 'sent', 'message': 'Windows accepted the approved command: ' + name}

    async def home(self, op):
        self.validate_home(op)
        if not self.settings.ha_url or not self.settings.ha_token:
            raise ValueError('Home Assistant is not configured; no command sent')
        domain = op['entity_id'].split('.')[0]
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.post(self.settings.ha_url + '/api/services/' + domain + '/' + op['service'], headers={'Authorization': 'Bearer ' + self.settings.ha_token}, json={k: v for k, v in op.items() if k != 'service'})
            if response.status_code != 200:
                raise ValueError(f'Home Assistant returned HTTP {response.status_code}; command not confirmed')
        return {'status': 'sent', 'message': 'Home Assistant accepted the service call; inspect state to confirm.', 'entity_id': op['entity_id']}

    async def devices(self):
        if not self.settings.ha_url or not self.settings.ha_token:
            return {'mode': 'demo', 'devices': [{'entity_id': 'demo.desk_lamp', 'name': 'Desk lamp — DEMO', 'state': 'not connected'}, {'entity_id': 'demo.rgb_strip', 'name': 'RGB strip — DEMO', 'state': 'not connected'}]}
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.get(self.settings.ha_url + '/api/states', headers={'Authorization': 'Bearer ' + self.settings.ha_token})
            if response.status_code != 200:
                raise ValueError(f'Home Assistant state read failed: HTTP {response.status_code}')
            return {'mode': 'real', 'devices': [{'entity_id': x['entity_id'], 'name': x.get('attributes', {}).get('friendly_name', x['entity_id']), 'state': x['state']} for x in response.json() if x['entity_id'] in self.settings.ha_entities]}

    def telemetry(self):
        try:
            battery = psutil.sensors_battery()
        except (OSError, NotImplementedError):
            battery = None
        return {'host_os': platform.system(), 'cpu_percent': psutil.cpu_percent(), 'memory_percent': psutil.virtual_memory().percent, 'battery_percent': battery.percent if battery else None, 'dry_run': self.settings.dry_run, 'tools_enabled': self.settings.tools_enabled}
