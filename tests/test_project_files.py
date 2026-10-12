"""Actual filesystem edits, approvals, backups and conflicts; no fabricated services."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from app.config import Settings, ROOT
from app.tools import ToolRegistry

async def approve(prompt): return True
async def decline(prompt): return False

class ProjectFileTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'workspace'
        self.settings = Settings(notes_dir=self.root/'notes', projects_dir=self.root, projects_write_dir=self.workspace, key='')
        self.tools = ToolRegistry(self.settings)

    def tearDown(self): self.temp.cleanup()

    async def test_create_read_edit_preview_backup_and_actual_readback(self):
        directory = await self.tools.call('create_directory', {'path':'School'}, approve)
        self.assertEqual(directory['status'], 'created')
        seen = []
        async def confirm(prompt): seen.append(prompt); return True
        result = await self.tools.call('create_file', {'path':'School/notes.md','content':'# Algebra\nStudy tomorrow.\n'}, confirm)
        self.assertIn('+# Algebra', seen[0])
        self.assertEqual(Path(result['path']).read_text(), '# Algebra\nStudy tomorrow.\n')
        original = await self.tools.call('read_file', {'path':result['path']}, approve)
        self.assertEqual(original['sha256'], hashlib.sha256(Path(result['path']).read_bytes()).hexdigest())
        changed = await self.tools.call('edit_file', {'path':'School/notes.md','old_text':'Study tomorrow.','new_text':'Study on Friday.','expected_sha256':original['sha256']}, confirm)
        self.assertIn('-Study tomorrow.', seen[1]);self.assertIn('+Study on Friday.',seen[1])
        self.assertEqual(Path(changed['path']).read_text(), '# Algebra\nStudy on Friday.\n')
        self.assertEqual(Path(changed['backup']).read_text(), '# Algebra\nStudy tomorrow.\n')
        files = await self.tools.call('list_files', {}, approve)
        self.assertIn('School/notes.md', files['writable_files'])
        self.assertFalse(any('.jarvis-backups' in f for f in files['files']+files['writable_files']))

    async def test_cancelled_creations_write_nothing(self):
        for name,args in [('create_file',{'path':'School/a.txt','content':'Hello'}),('create_directory',{'path':'School'})]:
            result = await self.tools.call(name,args,decline)
            self.assertEqual(result['status'],'cancelled')
            self.assertFalse(self.workspace.exists())

    async def test_existing_files_never_overwritten_and_empty_content_supported(self):
        await self.tools.call('create_file',{'path':'blank.txt','content':''},approve)
        self.assertEqual((self.workspace/'blank.txt').read_bytes(),b'')
        with self.assertRaises(ValueError):
            await self.tools.call('create_file',{'path':'blank.txt','content':'Overwrite'},approve)
        (self.workspace/'notes.txt').write_text('One passage.')
        data = await self.tools.call('read_file',{'path':str(self.workspace/'notes.txt')},approve)
        await self.tools.call('edit_file',{'path':'notes.txt','old_text':'One passage.','new_text':'','expected_sha256':data['sha256']},approve)
        self.assertEqual((self.workspace/'notes.txt').read_bytes(),b'')

    async def test_windows_crlf_edit_preserves_line_endings(self):
        await self.tools.call('create_file',{'path':'windows.txt','content':'First\r\nSecond\r\n'},approve)
        data = await self.tools.call('read_file',{'path':str(self.workspace/'windows.txt')},approve)
        await self.tools.call('edit_file',{'path':'windows.txt','old_text':'First\nSecond','new_text':'First\nUpdated','expected_sha256':data['sha256']},approve)
        self.assertEqual((self.workspace/'windows.txt').read_bytes(),b'First\r\nUpdated\r\n')

    async def test_file_changed_while_confirming_is_preserved(self):
        await self.tools.call('create_file',{'path':'notes.txt','content':'Original'},approve)
        original = await self.tools.call('read_file',{'path':str(self.workspace/'notes.txt')},approve)
        async def external_edit(prompt):
            (self.workspace/'notes.txt').write_text('Changed in my editor')
            return True
        args = {'path':'notes.txt','old_text':'Original','new_text':'Jarvis change','expected_sha256':original['sha256']}
        with self.assertRaises(ValueError): await self.tools.call('edit_file',args,external_edit)
        self.assertEqual((self.workspace/'notes.txt').read_text(),'Changed in my editor')
        with self.assertRaises(ValueError): await self.tools.call('edit_file',args,approve)

    async def test_file_created_while_confirming_is_preserved(self):
        async def external_create(prompt):
            self.workspace.mkdir();(self.workspace/'notes.txt').write_text('External file')
            return True
        with self.assertRaises(ValueError):
            await self.tools.call('create_file',{'path':'notes.txt','content':'Jarvis file'},external_create)
        self.assertEqual((self.workspace/'notes.txt').read_text(),'External file')

    async def test_path_traversal_private_binary_and_reserved_paths_rejected(self):
        for path in ['../outside.txt','/tmp/outside.txt','C:\\Windows\\notes.txt','sub/../../outside.txt','.env','sub/.env','credentials.json','token.json','image.pdf','program.exe','CON.txt','sub\\..\\outside.txt']:
            with self.subTest(path=path),self.assertRaises(ValueError):
                await self.tools.call('create_file',{'path':path,'content':'Blocked'},approve)
        self.assertFalse(self.workspace.exists())

    async def test_symlink_hardlink_and_unsafe_roots_rejected(self):
        self.workspace.mkdir();outside=self.root/'outside.txt';outside.write_text('Preserve')
        (self.workspace/'alias.txt').symlink_to(outside)
        with self.assertRaises(ValueError):
            await self.tools.call('create_file',{'path':'alias.txt','content':'Blocked'},approve)
        os.link(outside,self.workspace/'linked.txt')
        with self.assertRaises(ValueError):
            self.tools.validate('edit_file',{'path':'linked.txt','old_text':'Preserve','new_text':'Blocked','expected_sha256':hashlib.sha256(b'Preserve').hexdigest()})
        for root in [ROOT,ROOT/'app',self.settings.notes_dir,self.root]:
            settings=Settings(notes_dir=self.settings.notes_dir,projects_write_dir=root,key='')
            with self.assertRaises(ValueError):ToolRegistry(settings).validate('create_file',{'path':'test.txt','content':'Blocked'})
        self.assertEqual(outside.read_text(),'Preserve')

    async def test_ambiguous_edits_credentials_and_emergency_stop_rejected(self):
        await self.tools.call('create_file',{'path':'test.txt','content':'same same'},approve)
        read = await self.tools.call('read_file',{'path':str(self.workspace/'test.txt')},approve)
        with self.assertRaises(ValueError):
            await self.tools.call('edit_file',{'path':'test.txt','old_text':'same','new_text':'one','expected_sha256':read['sha256']},approve)
        self.settings.key='private-test-credential'
        (self.workspace/'test.txt').write_text(self.settings.key)
        with self.assertRaises(ValueError):
            await self.tools.call('edit_file',{'path':'test.txt','old_text':'private','new_text':'x','expected_sha256':hashlib.sha256(self.settings.key.encode()).hexdigest()},approve)
        self.settings.tools_enabled=False
        with self.assertRaises(ValueError):
            await self.tools.call('create_file',{'path':'blocked.txt','content':'Blocked'},approve)
        self.assertFalse((self.workspace/'blocked.txt').exists())
