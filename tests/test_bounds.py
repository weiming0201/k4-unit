"""Declared capacity and refusal boundaries; disposable local fixtures only."""
import importlib.util
import json
from pathlib import Path
import shutil
import signal
import unittest

spec=importlib.util.spec_from_file_location('recovery',Path(__file__).with_name('test_recovery.py'))
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
t=r.t


class BoundsTests(unittest.TestCase):
    setUp=t.UnitTests.setUp
    reload=t.UnitTests.reload
    request=t.UnitTests.request
    call=t.UnitTests.call
    project=t.UnitTests.project
    pending=t.UnitTests.pending
    start=t.UnitTests.start
    closeargs=t.UnitTests.closeargs
    work=t.UnitTests.work
    refuses=t.UnitTests.refuses
    child=r.RecoveryTests.child

    def test_file_and_transaction_exact_boundaries(self):
        S,L=self.p.storage,self.p.layout
        payload=b'x'*L.MAX_FILE
        self.assertEqual(len(S.unblob(S.blob(payload))),L.MAX_FILE)
        self.refuses('size',lambda:S.unblob(S.blob(payload+b'x')))
        tx=self.p.mechanics.Transaction(self.u.s)
        for i in range(L.MAX_TOTAL//L.MAX_FILE):
            tx.write('projects/meta/task/work/'+str(i),payload)
        self.assertEqual(tx.total,L.MAX_TOTAL)
        self.refuses('size',lambda:tx.write('projects/meta/task/work/excess',b'x'))
        # Construction refused before any files/receipts were persisted.
        self.assertFalse((self.ws/'projects/meta/task/work/0').exists())

    def test_text_items_and_package_bounds(self):
        L=self.p.layout
        self.assertEqual(len(self.p.storage.text('x'*L.MAX_TEXT)),L.MAX_TEXT)
        self.refuses('size',lambda:self.pending(body='x'*(L.MAX_TEXT+1)))
        item=self.pending()
        selected={k:item[k] for k in ('id','kind','sha256')}
        self.refuses('selection',lambda:self.call('task_start',project='meta',
            selected=[selected]*(L.MAX_ITEMS+1),task='bounded fixture',write_scopes=[]))
        self.refuses('size',lambda:self.u.call('check',{'unused':'x'*(L.MAX_TOTAL+1)}))
        adapter=t.module('bounded_adapter',self.ws/'projects/meta/tools/adapter.py')
        package=t.UnitTests.patch(self)
        package['patch'][0]['content']=self.p.storage.blob(b'x'*(4*1024*1024))
        with self.assertRaises(ValueError) as cm:
            adapter.apply(self.ws,package,'large-adapter')
        self.assertEqual(cm.exception.code,'size')
        self.assertIsNone(self.u.receipt('large-adapter-intake'))

    def test_tree_count_exact_boundaries(self):
        L=self.p.layout
        directory=self.ws/'projects/meta/task/work/tree'
        directory.mkdir()
        for i in range(L.MAX_FILES):
            (directory/str(i)).write_bytes(b'')
        self.assertEqual(len(self.u.s.tree('projects/meta/task/work/tree')),L.MAX_FILES)
        (directory/'one-more').write_bytes(b'')
        self.refuses('size',lambda:self.u.s.tree('projects/meta/task/work/tree'))

    def test_tree_byte_exact_boundaries(self):
        L=self.p.layout
        directory=self.ws/'projects/meta/task/work/tree'
        directory.mkdir()
        payload=b'x'*L.MAX_FILE
        for i in range(L.MAX_TOTAL//L.MAX_FILE):
            (directory/str(i)).write_bytes(payload)
        self.assertEqual(len(self.u.s.tree('projects/meta/task/work/tree')),4)
        (directory/'one-more').write_bytes(b'x')
        self.refuses('size',lambda:self.u.s.tree('projects/meta/task/work/tree'))

    def test_adapter_cannot_write_understanding_or_escape(self):
        adapter=t.module('scope_adapter',self.ws/'projects/meta/tools/adapter.py')
        for path in ('understanding/description.md','../focus.md','object/../rules.md'):
            package=t.UnitTests.patch(self)
            package['patch'][0]['path']=path
            with self.assertRaises(ValueError) as cm:
                adapter.apply(self.ws,package,'invalid-adapter')
            self.assertIn(cm.exception.code,('adapter-scope','path'))
        self.assertIsNone(self.u.receipt('invalid-adapter-intake'))
        self.assertIsNone(self.u.manifest()['projects']['meta']['active'])

    def test_real_crash_then_third_version_is_preserved(self):
        project=self.project()
        item,task=self.start(project)
        self.work(project,'out',b'planned')
        destination='projects/'+project+'/object/result'
        args=self.closeargs(item,task,request_id='third-version',
            writes=[dict(path='object/result',from_work='out')])
        payload=dict(operation='task_close',arguments=args)
        probe=Path(self.temp.name)/'probe'
        shutil.copytree(self.ws,probe)
        result=self.child('call',probe,payload,0)
        self.assertEqual(result.returncode,0,result.stderr)
        events=[json.loads(line) for line in result.stdout.splitlines()]
        cut=next(v['checkpoint'] for v in events if v.get('phase')=='after'
                 and v.get('operation')=='replace' and v.get('path')==destination)
        killed=self.child('call',self.ws,payload,cut)
        self.assertEqual(killed.returncode,-signal.SIGKILL,killed.stderr)
        (self.ws/destination).write_bytes(b'independent third version')
        receipt=self.u.receipt('third-version')
        old=t.module('conflict_snapshot',self.ws/'receipts/engines'/receipt['engine']/'cli.py')
        frozen=old.load_kernel(self.ws)
        unit=frozen.mechanics.Unit(self.ws)
        with self.assertRaises(frozen.storage.Refused) as cm:
            unit.recover('third-version')
        self.assertEqual(cm.exception.code,'conflict')
        self.assertEqual((self.ws/destination).read_bytes(),b'independent third version')
        self.assertEqual(self.u.receipt('third-version')['state'],'pending')
        self.assertIsNotNone(self.u.manifest()['projects'][project]['active'])


if __name__=='__main__':
    unittest.main(verbosity=2)
