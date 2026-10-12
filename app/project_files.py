"""Confirmed text-file changes confined to a dedicated workspace."""
import difflib
import hashlib
import os
from pathlib import Path
import re
import tempfile
import uuid

TEXT_TYPES = {'.txt', '.md', '.py', '.js', '.ts', '.tsx', '.jsx', '.json', '.yaml', '.yml', '.html', '.css', '.csv', '.r', '.tex', '.sql', '.ipynb', '.c', '.cpp', '.h'}
MAX_FILE_BYTES = 256_000


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ProjectFiles:
    def __init__(self, settings):
        self.settings = settings
        self.root = settings.projects_write_dir

    def check_root(self):
        from .config import ROOT
        root = self.root
        if root.is_symlink() or root.resolve() != root:
            raise ValueError('Writable workspace changed into a symlink.')
        notes = self.settings.notes_dir
        forbidden = [notes, ROOT / 'app', ROOT / 'ui', ROOT / 'docs', ROOT / 'tests', ROOT / '.git', ROOT / '.venv']
        if ROOT.is_relative_to(root) or root == Path(root.anchor):
            raise ValueError('Do not grant writes to the application folder, its parents or an entire drive.')
        if any(root.is_relative_to(p) or p.is_relative_to(root) for p in forbidden):
            raise ValueError('Writable workspace must be separate from notes, credentials and application files.')
        return root

    def path(self, value, directory=False):
        root = self.check_root()
        value = value.replace('\\', '/')
        pieces = value.split('/')
        if len(value) > 500 or len(pieces) > 12 or any(not p or p in {'.', '..'} or p.startswith('.') or p.endswith((' ', '.')) for p in pieces):
            raise ValueError('Use a normal relative path inside JarvisProjects; no traversal or hidden paths.')
        if any(re.search(r'[<>:"|?*\x00-\x1f]', p) or re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', p, re.I) for p in pieces):
            raise ValueError('Invalid or reserved Windows filename.')
        if any(p.lower() in {'private', '__pycache__', 'node_modules'} for p in pieces):
            raise ValueError('Internal paths cannot be edited.')
        candidate = root
        for piece in pieces:
            candidate /= piece
            if candidate.is_symlink():
                raise ValueError('Symlinks are not allowed in writable paths.')
        if not candidate.resolve().is_relative_to(root):
            raise ValueError('Write path is outside the authorized workspace.')
        if candidate == self.settings.credentials_file.resolve() or candidate.name.lower() in {'credentials.json', 'token.json'}:
            raise ValueError('Credential files cannot be edited.')
        if not directory and candidate.suffix.lower() not in TEXT_TYPES:
            raise ValueError('Only supported text/code files can be created or edited; PDFs and binaries are read-only.')
        if candidate.exists() and not directory and not candidate.is_file():
            raise ValueError('Target must be a regular file.')
        if candidate.is_file() and candidate.stat().st_nlink > 1:
            raise ValueError('Hard-linked files cannot be edited.')
        return candidate

    def content(self, data):
        if len(data) > MAX_FILE_BYTES:
            raise ValueError('Editable files are limited to 256 KB.')
        text = data.decode('utf-8')
        if '\x00' in text:
            raise ValueError('Binary files cannot be edited.')
        if any(secret and secret in text for secret in (self.settings.key, self.settings.ha_token)):
            raise ValueError('This file contains configured credentials and cannot be edited by Jarvis.')
        return text

    def prepare(self, name, args):
        directory = name == 'create_directory'
        path = self.path(args['path'], directory)
        relative = str(path.relative_to(self.root))
        if directory:
            if path.exists(): raise ValueError('Directory already exists; no change is needed.')
            return {'path': path, 'relative': relative, 'preview': 'Create directory: ' + relative}
        if name == 'create_file':
            if path.exists(): raise ValueError('File already exists. Read it and use edit_file; existing files are never overwritten by create_file.')
            old = None
            new = args['content'].encode('utf-8')
            self.content(new)
        else:
            if not path.is_file(): raise ValueError('File does not exist. Use create_file.')
            old = path.read_bytes()
            old_text = self.content(old)
            if digest(old) != args['expected_sha256']:
                raise ValueError('File changed since it was read. Read the latest version before editing.')
            needle, replacement = args['old_text'], args['new_text']
            if old_text.count(needle) == 0 and '\r\n' in old_text:
                needle = needle.replace('\r\n', '\n').replace('\n', '\r\n')
            if old_text.count(needle) != 1:
                raise ValueError('old_text must match exactly once. Read the file and provide a unique exact passage.')
            if '\r\n' in old_text:
                replacement = replacement.replace('\r\n', '\n').replace('\n', '\r\n')
            new = old_text.replace(needle, replacement, 1).encode('utf-8')
            self.content(new)
            if old == new: raise ValueError('No change was proposed.')
        before = self.content(old) if old is not None else ''
        after = self.content(new)
        preview = '\n'.join(difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile=relative + ' (before)', tofile=relative + ' (after)', lineterm=''))
        if len(preview) > 24000:
            raise ValueError('Change preview is too large; request a smaller edit.')
        return {'path': path, 'relative': relative, 'old': old, 'new': new, 'preview': preview or '[Create an empty text file]'}

    def apply(self, name, args, proposal):
        path = self.path(args['path'], name == 'create_directory')
        if path != proposal['path']: raise ValueError('Target changed after confirmation.')
        if name == 'create_directory':
            path.mkdir(parents=True, exist_ok=False)
            return {'status': 'created', 'path': str(path), 'message': 'Directory created.'}
        old, new = proposal['old'], proposal['new']
        if old is None and path.exists(): raise ValueError('A file appeared after confirmation; nothing was overwritten.')
        if old is not None and (not path.is_file() or path.read_bytes() != old):
            raise ValueError('File changed during confirmation; nothing was overwritten. Read it and try again.')
        path.parent.mkdir(parents=True, exist_ok=True)
        backup = None
        if old is not None:
            backups = self.root / '.jarvis-backups'
            if backups.is_symlink() or not backups.resolve().is_relative_to(self.root):
                raise ValueError('Backup directory escapes the writable workspace.')
            backups.mkdir(exist_ok=True)
            backup = backups / (uuid.uuid4().hex + '__' + path.name + '.bak')
            with backup.open('xb') as handle:
                handle.write(old);handle.flush();os.fsync(handle.fileno())
        if old is None:
            # Exclusive creation: never replace a file created while confirmation was open.
            with path.open('xb') as handle:
                handle.write(new);handle.flush();os.fsync(handle.fileno())
        else:
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.jarvis-', delete=False) as handle:
                    temporary = Path(handle.name)
                    handle.write(new);handle.flush();os.fsync(handle.fileno())
                self.path(args['path'])
                if path.read_bytes() != old: raise ValueError('File changed before saving; original was not overwritten.')
                os.replace(temporary, path)
            finally:
                if temporary: temporary.unlink(missing_ok=True)
        if path.read_bytes() != new: raise RuntimeError('File read-back verification failed.')
        return {'status': 'created' if old is None else 'saved', 'path': str(path), 'relative_path': proposal['relative'], 'sha256': digest(new), 'backup': str(backup) if backup else None, 'message': 'Actual file write verified by read-back.'}
