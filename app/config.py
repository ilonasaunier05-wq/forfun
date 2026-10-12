import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')

def local_path(name, default):
    path = Path(os.path.expandvars(os.path.expanduser(os.getenv(name, str(default)))))
    return (path if path.is_absolute() else ROOT / path).resolve()

@dataclass
class Settings:
    notes_dir: Path = field(default_factory=lambda: local_path('NOTES_DIR', ROOT / 'data'))
    projects_dir: Path = field(default_factory=lambda: local_path('PROJECTS_DIR', ROOT))
    projects_write_dir: Path = field(default_factory=lambda: local_path('PROJECTS_WRITE_DIR', ROOT / 'JarvisProjects'))
    key: str = field(default_factory=lambda: os.getenv('GROQ_API_KEY', ''), repr=False)
    model: str = field(default_factory=lambda: os.getenv('GROQ_MODEL', 'openai/gpt-oss-20b'))
    fallback_model: str = field(default_factory=lambda: os.getenv('GROQ_FALLBACK_MODEL', 'llama-3.1-8b-instant'))
    whisper_model: str = field(default_factory=lambda: os.getenv('WHISPER_MODEL', 'whisper-large-v3-turbo'))
    language: str = field(default_factory=lambda: os.getenv('JARVIS_LANGUAGE', 'en'))
    voice: str = field(default_factory=lambda: os.getenv('TTS_VOICE', ''))
    timezone: str = field(default_factory=lambda: os.getenv('JARVIS_TIMEZONE', 'Europe/Paris'))
    max_output: int = field(default_factory=lambda: int(os.getenv('JARVIS_MAX_OUTPUT_TOKENS', '1200')))
    password: str = field(default_factory=lambda: os.getenv('JARVIS_PASSWORD', ''), repr=False)
    allowed_hosts: list = field(default_factory=lambda: [x.strip().lower() for x in os.getenv('JARVIS_ALLOWED_HOSTS', 'localhost,127.0.0.1,::1').split(',')])
    secure_cookie: bool = field(default_factory=lambda: os.getenv('JARVIS_SECURE_COOKIE', 'false').lower() == 'true')
    ha_url: str = field(default_factory=lambda: os.getenv('HA_URL', '').rstrip('/'))
    ha_token: str = field(default_factory=lambda: os.getenv('HA_TOKEN', ''), repr=False)
    ha_entities: list = field(default_factory=lambda: [x.strip() for x in os.getenv('HA_ENTITIES', '').split(',') if x.strip()])
    credentials_file: Path = field(default_factory=lambda: local_path('GOOGLE_CREDENTIALS_FILE', ROOT / 'credentials.json'))
    input_device: str = field(default_factory=lambda: os.getenv('AUDIO_INPUT_DEVICE', ''))
    clap_sensitivity: float = field(default_factory=lambda: float(os.getenv('CLAP_SENSITIVITY', '6')))
    silence_seconds: float = field(default_factory=lambda: float(os.getenv('SILENCE_SECONDS', '0.9')))
    config_file: Path = field(default_factory=lambda: ROOT / 'config.yaml')
    followup_seconds: float = field(default_factory=lambda: float(os.getenv('VOICE_FOLLOWUP_SECONDS', '0')))
    tools_enabled: bool = True

    def __post_init__(self):
        self.notes_dir = Path(self.notes_dir).resolve()
        self.projects_dir = Path(self.projects_dir).resolve()
        self.projects_write_dir = Path(self.projects_write_dir).resolve()
        self.data_dir = self.notes_dir
        self.memory_file = self.notes_dir / 'memory.md'
        self.private_dir = self.notes_dir / '.private'
        self.tz = ZoneInfo(self.timezone)
        if not 0 <= self.followup_seconds <= 60:
            raise ValueError('VOICE_FOLLOWUP_SECONDS must be between 0 and 60.')
        if self.language not in {'en', 'fr'}:
            raise ValueError('JARVIS_LANGUAGE must be en or fr.')
        self.voice = self.voice or 'en-GB-RyanNeural'
        if not 2 <= self.clap_sensitivity <= 30 or not 0.3 <= self.silence_seconds <= 3:
            raise ValueError('Invalid clap sensitivity or silence interval.')
        if self.ha_url and not self.ha_url.startswith(('http://', 'https://')):
            raise ValueError('HA_URL must use HTTP(S).')
        self.app_config = yaml.safe_load(self.config_file.read_text(encoding='utf-8')) if self.config_file.exists() else {}
        if not isinstance(self.app_config, dict) or not isinstance(self.app_config.get('apps', {}), dict):
            raise ValueError('config.yaml must contain an apps mapping.')
