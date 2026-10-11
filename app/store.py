import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

CATEGORIES = ('Profile', 'Preferences', 'Home', 'Projects', 'Routines')

def now():
    return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.memory_dir = self.directory / 'memory'
        if not self.memory_dir.resolve().is_relative_to(self.directory):
            raise ValueError('Memory export directory escapes NOTES_DIR.')
        self.memory_dir.mkdir(exist_ok=True)
        if not (self.directory / 'jarvis.sqlite3').resolve().is_relative_to(self.directory):
            raise ValueError('Database path escapes NOTES_DIR.')
        if not (self.directory / 'jarvis.sqlite3').exists() and any((self.memory_dir / (c + '.md')).exists() for c in CATEGORIES):
            raise ValueError('Existing memory Markdown found without a JARVIS database. Choose a new data directory; no files were overwritten.')
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.directory / 'jarvis.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, title TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, session TEXT REFERENCES sessions(id), role TEXT, content TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY, category TEXT, content TEXT, created TEXT);
        CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(id UNINDEXED, content);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS actions(id INTEGER PRIMARY KEY, action TEXT, result TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS usage(id TEXT PRIMARY KEY, session TEXT, day TEXT, provider TEXT, model TEXT, input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, reserved_cost REAL DEFAULT 0, actual_cost REAL, status TEXT);
        ''')
        self.db.commit()
        self.sync_markdown()

    def rows(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args)]

    def execute(self, sql, args=()):
        with self.lock, self.db:
            self.db.execute(sql, args)

    def session(self):
        sid = str(uuid.uuid4())
        self.execute('INSERT INTO sessions VALUES(?,?,?)', (sid, 'New conversation', now()))
        return sid

    def require_session(self, sid):
        if not self.rows('SELECT id FROM sessions WHERE id=?', (sid,)):
            raise ValueError('Unknown conversation')

    def message(self, sid, role, text):
        self.require_session(sid)
        with self.lock, self.db:
            self.db.execute('INSERT INTO messages(session,role,content,created) VALUES(?,?,?,?)', (sid, role, text, now()))
            if role == 'user':
                self.db.execute("UPDATE sessions SET title=? WHERE id=? AND title='New conversation'", (text[:70], sid))

    def history(self, sid, limit=20):
        self.require_session(sid)
        return self.rows('SELECT role,content,created FROM (SELECT * FROM messages WHERE session=? ORDER BY id DESC LIMIT ?) ORDER BY id', (sid, limit))

    def memory(self, content, category, mid=None):
        if category not in CATEGORIES or not content.strip():
            raise ValueError('Choose a valid category and nonempty memory')
        with self.lock, self.db:
            existing = self.db.execute('SELECT id FROM memories WHERE content=? AND category=?', (content.strip(), category)).fetchone()
            if existing and not mid:
                return existing['id']
            if mid and not self.db.execute('SELECT id FROM memories WHERE id=?', (mid,)).fetchone():
                raise ValueError('Unknown memory')
            mid = mid or str(uuid.uuid4())
            self.db.execute('INSERT OR REPLACE INTO memories VALUES(?,?,?,?)', (mid, category, content.strip(), now()))
            self.db.execute('DELETE FROM memory_fts WHERE id=?', (mid,))
            self.db.execute('INSERT INTO memory_fts VALUES(?,?)', (mid, content.strip()))
            self.sync_markdown()
        return mid

    def forget(self, mid):
        with self.lock, self.db:
            self.db.execute('DELETE FROM memories WHERE id=?', (mid,))
            self.db.execute('DELETE FROM memory_fts WHERE id=?', (mid,))
            self.sync_markdown()

    def search(self, query, limit=6):
        words = re.findall(r'\w+', query, re.UNICODE)[:20]
        if not words:
            return []
        match = ' OR '.join('"' + w + '"' for w in words)
        return self.rows('SELECT m.* FROM memory_fts f JOIN memories m ON m.id=f.id WHERE memory_fts MATCH ? ORDER BY rank LIMIT ?', (match, limit))

    def sync_markdown(self):
        # These five files are app-managed exports; edit memories in the inspector.
        with self.lock:
            for category in CATEGORIES:
                entries = self.rows('SELECT * FROM memories WHERE category=? ORDER BY created', (category,))
                text = '# ' + category + '\n\n<!-- JARVIS managed export: edit through the memory inspector. -->\n\n'
                for m in entries:
                    text += f"## {m['id']}\n\n{m['content']}\n\n"
                target = self.memory_dir / (category + '.md')
                temp = target.with_suffix('.md.tmp')
                if not temp.resolve().is_relative_to(self.directory):
                    raise ValueError('Memory export temporary path escapes NOTES_DIR.')
                temp.write_text(text, encoding='utf-8')
                temp.replace(target)

    def log_action(self, action, result):
        self.execute('INSERT INTO actions(action,result,created) VALUES(?,?,?)', (json.dumps(action), json.dumps(result), now()))
