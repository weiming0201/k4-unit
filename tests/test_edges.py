"""Boundary tests independent of task happy paths."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import unittest
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('unit_tests',Path(__file__).with_name('test_unit.py'))
t=importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


class EdgeTests(unittest.TestCase):
    setUp=t.UnitTests.setUp
    reload=t.UnitTests.reload
    request=t.UnitTests.request
    call=t.UnitTests.call
    project=t.UnitTests.project
    pending=t.UnitTests.pending
    start=t.UnitTests.start
    closeargs=t.UnitTests.closeargs
    close=t.UnitTests.close
    work=t.UnitTests.work
    refuses=t.UnitTests.refuses

    def test_empty_target_replaced_and_permissions_private(self):
        dest=Path(self.temp.name)/'empty space'
        dest.mkdir()
        old=dest.stat().st_ino
        self.assertTrue(t.INSTALL.install(dest)['ok'])
        self.assertNotEqual(dest.stat().st_ino,old)
        for p in [dest,*dest.rglob('*')]:
            self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o700 if p.is_dir() else 0o600,str(p))

    def test_parent_alias_allowed_target_symlink_file_nonempty_refused(self):
        root=Path(self.temp.name)
        (root/'parent-alias').symlink_to(root,target_is_directory=True)
        self.assertTrue(t.INSTALL.install(root/'parent-alias'/'new')['ok'])
        (root/'target-link').symlink_to(root/'new',target_is_directory=True)
        (root/'file').write_bytes(b'original')
        for name in ('target-link','file','ws'):
            self.assertFalse(t.INSTALL.install(root/name)['ok'])
        self.assertEqual((root/'file').read_bytes(),b'original')

    def test_parent_busy_refuses_without_staging(self):
        fd=os.open(self.temp.name,os.O_RDONLY|os.O_DIRECTORY)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            before=set(Path(self.temp.name).iterdir())
            result=t.INSTALL.install(Path(self.temp.name)/'new')
            self.assertEqual(result['code'],'parent-busy')
            self.assertEqual(before,set(Path(self.temp.name).iterdir()))
        finally:
            os.close(fd)

    def test_host_entries_shape_not_binding(self):
        m=self.u.manifest()
        (self.ws/'AGENTS.md').write_text('Not a registration proof',encoding='utf-8')
        self.assertFalse(self.call('check',scope='workspace')['ok'])
        m['host_entries']={'AGENTS.md':'file'}
        (self.ws/'manifest.json').write_bytes(self.p.storage.encode(m))
        self.assertTrue(self.call('check',scope='workspace')['ok'])
        m['host_entries']={'projects':'directory'}
        (self.ws/'manifest.json').write_bytes(self.p.storage.encode(m))
        self.assertFalse(self.call('check',scope='workspace')['ok'])

    def test_check_is_read_only_and_other_project_not_read(self):
        project=self.project()
        before={str(p.relative_to(self.ws)):(p.stat().st_mtime_ns,p.stat().st_size) for p in self.ws.rglob('*')}
        seen=[]
        original=self.u.s.read
        def read(path,*a,**kw):
            seen.append(path)
            return original(path,*a,**kw)
        self.u.s.read=read
        self.assertTrue(self.call('check',scope='project',project=project)['ok'])
        self.assertFalse([x for x in seen if x.startswith('projects/meta/')])
        after={str(p.relative_to(self.ws)):(p.stat().st_mtime_ns,p.stat().st_size) for p in self.ws.rglob('*')}
        self.assertEqual(before,after)

    def test_workspace_write_lock_is_short_and_observable(self):
        with self.u.s.lock():
            self.refuses('busy',lambda:self.pending())
        self.pending()

    def test_two_real_processes_cannot_claim_same_task(self):
        item=self.pending()
        cli=self.ws/'projects/meta/object/mcp/cli.py'
        requests=[]
        for i in range(2):
            args=dict(project='meta',selected=[{k:item[k] for k in ('id','kind','sha256')}],
                task='One owner only.',write_scopes=[],request_id='contender-'+str(i))
            requests.append(subprocess.Popen([sys.executable,'-I','-S','-B',str(cli),'--workspace',str(self.ws),
                'call','task_start','--input','-'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE))
            requests[-1].stdin.write(json.dumps(args).encode())
            requests[-1].stdin.close()
        results=[]
        for proc in requests:
            proc.wait(timeout=15)
            results.append(json.loads(proc.stdout.read()))
            proc.stdout.close();proc.stderr.close()
        self.assertEqual(sum(x['ok'] for x in results),1,results)
        self.assertIn(next(x['code'] for x in results if not x['ok']),('busy','active-task'))

    def test_receipt_parent_symlink_refused(self):
        directory=self.ws/'receipts/requests'
        directory.rename(self.ws/'receipts/saved-requests')
        outside=Path(self.temp.name)/'outside'
        outside.mkdir()
        directory.symlink_to(outside,target_is_directory=True)
        self.refuses('symlink',lambda:self.pending())
        self.assertFalse(any(outside.iterdir()))

    def test_archive_occupied_refuses_before_writeback(self):
        project=self.project()
        item,task=self.start(project)
        self.work(project,'out',b'new')
        archive=self.ws/'archive'/project/task['task_id']
        archive.mkdir(parents=True)
        (archive/'unrelated').write_bytes(b'keep')
        self.refuses('conflict',lambda:self.close(item,task,writes=[dict(path='object/out',from_work='out')]))
        self.assertFalse((self.ws/'projects'/project/'object/out').exists())
        self.assertEqual((archive/'unrelated').read_bytes(),b'keep')

    def test_missing_snapshot_refuses_without_current_fallback(self):
        item,task=self.start(scopes=[])
        snapshot=self.ws/'receipts/engines'/task['engine']/'mechanics.py'
        snapshot.write_bytes(b'# tampered')
        self.refuses('snapshot',lambda:self.close(item,task))
        self.assertIsNotNone(self.u.manifest()['projects']['meta']['active'])

    def test_bounded_semantic_inputs_rejected(self):
        self.refuses('size',lambda:self.pending(body='x'*(self.p.layout.MAX_TEXT+1)))
        self.refuses('path',lambda:self.call('pending_add',project='meta',kind='target',source_refs=['fixture'],
            body='bad path',files={'../escape':'eA=='}))


if __name__=='__main__':
    unittest.main(verbosity=2)
