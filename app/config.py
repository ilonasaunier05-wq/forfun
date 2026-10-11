import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')

@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv('JARVIS_DATA_DIR', str(ROOT / 'data'))))
    password: str = field(default_factory=lambda: os.getenv('JARVIS_PASSWORD', ''))
    allowed_hosts: list = field(default_factory=lambda: [x.strip().lower() for x in os.getenv('JARVIS_ALLOWED_HOSTS', 'localhost,127.0.0.1,::1').split(',')])
    secure_cookie: bool = field(default_factory=lambda: os.getenv('JARVIS_SECURE_COOKIE', 'false').lower() == 'true')
    dry_run: bool = field(default_factory=lambda: os.getenv('JARVIS_DRY_RUN', 'true').lower() != 'false')
    tools_enabled: bool = True
    free_mode: bool = field(default_factory=lambda: os.getenv('JARVIS_FREE_MODE', 'true').lower() != 'false')
    ha_url: str = field(default_factory=lambda: os.getenv('HA_URL', '').rstrip('/'))
    ha_token: str = field(default_factory=lambda: os.getenv('HA_TOKEN', ''))
    ha_entities: list = field(default_factory=lambda: [x.strip() for x in os.getenv('HA_ENTITIES', '').split(',') if x.strip()])
    search_key: str = field(default_factory=lambda: os.getenv('BRAVE_SEARCH_API_KEY', ''))
    max_output: int = field(default_factory=lambda: int(os.getenv('JARVIS_MAX_OUTPUT_TOKENS', '1024')))
    daily_requests: int = field(default_factory=lambda: int(os.getenv('JARVIS_DAILY_REQUEST_LIMIT', '100')))
    daily_budget: float = field(default_factory=lambda: float(os.getenv('JARVIS_DAILY_BUDGET_USD', '0')))
    providers: dict = field(default_factory=dict)
    scenes_file: Path = field(default_factory=lambda: ROOT / 'scenes.json')

    def __post_init__(self):
        if not self.providers:
            self.providers = {
                'openai': {'url': 'https://api.openai.com/v1', 'key': os.getenv('OPENAI_API_KEY', '') or os.getenv('JARVIS_OPENAI_KEY', ''), 'models': os.getenv('OPENAI_MODELS', 'gpt-4.1-mini,gpt-4.1').split(',')},
                'compatible': {'url': os.getenv('AI_BASE_URL', 'https://api.groq.com/openai/v1').rstrip('/'), 'key': os.getenv('GROQ_API_KEY', '') or os.getenv('AI_API_KEY', ''), 'models': os.getenv('AI_MODELS', 'llama-3.3-70b-versatile').split(',')},
            }
        if self.free_mode:
            # Endpoint and model allowlist prevents switching to an arbitrary paid API.
            compatible = self.providers.get('compatible')
            self.providers = {'compatible': compatible} if compatible and compatible['url'] == 'https://api.groq.com/openai/v1' else {}
            self.search_key = ''
            if not self.providers:
                raise ValueError('Free mode requires the Groq endpoint https://api.groq.com/openai/v1. Paid provider fallback is disabled.')
        # User-supplied rates, USD per million input/output tokens. No invented cost estimate.
        self.rates = json.loads(os.getenv('JARVIS_MODEL_RATES_JSON', '{}'))
        if not isinstance(self.rates, dict) or any(not isinstance(v, list) or len(v) != 2 or any(type(rate) not in (int, float) or rate < 0 for rate in v) for v in self.rates.values()):
            raise ValueError('Model rates must map provider/model to two nonnegative prices.')
        for p in self.providers.values():
            if not p['url'].startswith('https://'):
                raise ValueError('AI provider endpoints must use HTTPS.')
        if self.ha_url and not self.ha_url.startswith(('https://', 'http://')):
            raise ValueError('HA_URL must be an HTTP(S) URL.')
        if self.max_output < 1 or self.daily_requests < 1 or self.daily_budget < 0:
            raise ValueError('Usage limits must be positive (budget may be zero to disable).')
