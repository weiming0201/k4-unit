"""Literal r4 boundaries not established by the original happy-path cases."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('base',Path(__file__).with_name('test_unit.py'))
t=importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


class R4Tests(unittest.TestCase):
    setUp=t.UnitTests.setUp
    reload=t.UnitTests.reload
    request=t.UnitTests.request
    call=t.UnitTests.call
    project=t.UnitTests.project
    pending=t.UnitTests.pending
    start=t.UnitTests.start
    work=t.UnitTests.work
    close=t.UnitTests.close
    closeargs=t.UnitTests.closeargs
    refuses=t.UnitTests.refuses

    def test_empty_reserved_directory_is_visible_to_meta_and_all_checks(self):
        (self.ws/'projects/meta/object/skills/unit-extra').mkdir()
        self.assertTrue(self.call('check',scope='workspace')['ok'])
        for args in (dict(scope='project',project='meta'),dict(scope='all')):
            with self.subTest(args=args):
                result=self.call('check',**args)
                self.assertFalse(result['ok'],result)
                self.assertTrue(any(i.get('code')=='reserved-skill' for i in result['issues']),result)
                self.assertNotIn('meta',result['baselines'])

    def test_adoption_cannot_bless_an_extra_empty_reserved_directory(self):
        item,started=self.start()
        (self.ws/'projects/meta/object/skills/unit-extra').mkdir()
        self.work('meta','result',b'authorized fixture content')
        manifest=(self.ws/'manifest.json').read_bytes()
        self.refuses('reserved-skill',lambda:self.close(item,started,
            writes=[dict(path='object/fixture.txt',from_work='result')]))
        self.assertEqual((self.ws/'manifest.json').read_bytes(),manifest)
        self.assertFalse((self.ws/'projects/meta/object/fixture.txt').exists())
        self.assertEqual(self.u.manifest()['projects']['meta']['active']['id'],started['task_id'])

    def test_empty_nonunit_instance_namespace_remains_legal(self):
        (self.ws/'projects/meta/object/skills/self-example').mkdir()
        self.assertTrue(self.call('check',scope='all')['ok'])
        item,started=self.start()
        self.work('meta','result',b'ordinary update')
        self.close(item,started,writes=[dict(path='object/fixture.txt',from_work='result')])
        self.assertTrue(self.call('check',scope='all')['ok'])

    def test_both_structural_paths_report_affected_task_and_kernel(self):
        project=self.project()
        other,old=self.start(project,scopes=[])
        item,started=self.start()
        original=(self.ws/'projects/meta/object/mcp/layout.py').read_bytes()
        cases=[('object/workspace.json',self.p.storage.encode(dict(self.p.layout.contract(),contract='incompatible'))),
               ('object/mcp/layout.py',original.replace(b"CONTRACT = 'unit-workspace/6'",b"CONTRACT = 'incompatible'"))]
        manifest=(self.ws/'manifest.json').read_bytes()
        for target,payload in cases:
            with self.subTest(target=target):
                self.work('meta','candidate',payload)
                with self.assertRaises(self.p.storage.Refused) as caught:
                    self.close(item,started,writes=[dict(path=target,from_work='candidate')])
                report=caught.exception.report()
                self.assertEqual(report['code'],'active-old-contract')
                self.assertEqual(report['projects'],[project])
                self.assertEqual(report.get('tasks'),[dict(project=project,task_id=old['task_id'],engine=old['engine'])])
                self.assertEqual((self.ws/'manifest.json').read_bytes(),manifest)
        self.close(other,old)


if __name__=='__main__':
    unittest.main(verbosity=2)
