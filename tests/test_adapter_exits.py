"""Adapter refusal exits; actual returned old-kernel CLI is executed in fixtures."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_unit as t


class AdapterExitTests(unittest.TestCase):
    setUp=t.UnitTests.setUp
    reload=t.UnitTests.reload
    request=t.UnitTests.request
    call=t.UnitTests.call
    project=t.UnitTests.project
    pending=t.UnitTests.pending
    start=t.UnitTests.start
    adapter=t.UnitTests.adapter
    patch=t.UnitTests.patch

    def rejected(self,package,request='reject',observer=None):
        try:self.adapter().apply(self.ws,package,request,observer=observer)
        except Exception as e:
            self.assertTrue(hasattr(e,'report'),repr(e))
            return e.report()
        self.fail('Expected refusal')

    def no_intake(self):
        self.assertIsNone(self.u.manifest()['projects']['meta']['active'])
        self.assertEqual(list((self.ws/'projects/meta/pending/target').glob('*.json')),[])

    def execute_abandon(self,error):
        action=error['adapter_exits']['abandon']
        self.assertIn('/receipts/engines/',action['command'][4])
        result=subprocess.run(action['command'],input=json.dumps(action['input']),text=True,
            capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        value=json.loads(result.stdout)
        self.assertEqual(value['outcome'],'incomplete')
        self.assertIsNone(self.u.manifest()['projects']['meta']['active'])
        return value

    def test_reserved_patch_refused_before_intake(self):
        pkg=self.patch();pkg['patch'][0]['path']='object/skills/unit-extra/SKILL.md'
        error=self.rejected(pkg)
        self.assertEqual(error['code'],'reserved-skill')
        self.no_intake()

    def test_structural_json_refused_before_intake_even_with_other_task(self):
        project=self.project();self.start(project)
        pkg=self.patch();path='object/workspace.json'
        value=self.u.s.json('projects/meta/'+path);value['contract']='future-contract'
        pkg['patch']=[dict(path=path,before=self.u.s.digest('projects/meta/'+path),
            content=self.p.storage.blob(self.p.storage.encode(value)))]
        error=self.rejected(pkg)
        self.assertEqual(error['code'],'active-old-contract')
        self.assertEqual(error['projects'],[project])
        self.no_intake()

    def test_structural_layout_refused_before_intake(self):
        pkg=self.patch();path='object/mcp/layout.py'
        body=self.u.s.read('projects/meta/'+path).replace(b"unit-workspace/6",b"unit-workspace/99")
        pkg['patch']=[dict(path=path,before=self.u.s.digest('projects/meta/'+path),content=self.p.storage.blob(body))]
        error=self.rejected(pkg)
        self.assertEqual(error['code'],'migration-required')
        self.no_intake()

    def test_conditional_refusal_offers_exits_same_request_can_retry(self):
        extra=self.ws/'projects/meta/object/skills/unit-extra';extra.mkdir()
        pkg=self.patch();error=self.rejected(pkg)
        self.assertEqual(error['code'],'reserved-skill')
        self.assertEqual(error['adapter_exits']['retry']['request_id'],'reject')
        self.assertIn('abandon',error['adapter_exits'])
        self.assertIsNotNone(self.u.manifest()['projects']['meta']['active'])
        extra.rmdir()
        result=self.adapter().apply(self.ws,pkg,'reject')
        self.assertTrue(result['ok'])
        self.assertTrue(self.u.check(scope='all')['ok'])

    def test_racing_external_write_preserved_by_explicit_abandon(self):
        pkg=self.patch();changed=False
        def race(phase,operation,path):
            nonlocal changed
            if not changed and phase=='after' and operation=='replace' and path=='projects/meta/task/work/adapter/0.payload':
                changed=True
                (self.ws/'projects/meta/tools/fixture.py').write_bytes(b'other-writer')
        error=self.rejected(pkg,observer=race)
        self.assertTrue(changed)
        self.assertEqual(error['code'],'stale')
        self.execute_abandon(error)
        self.assertEqual((self.ws/'projects/meta/tools/fixture.py').read_bytes(),b'other-writer')
        self.assertEqual(self.rejected(pkg)['code'],'adapter-task')
        pkg['patch'][1]['before']=self.u.s.digest('projects/meta/tools/fixture.py')
        self.assertTrue(self.adapter().apply(self.ws,pkg,'corrected')['ok'])
        self.assertEqual(len(list((self.ws/'projects/meta/pending/target').glob('*.json'))),1)
        self.assertTrue(self.u.check(scope='all')['ok'])

    def test_durable_close_intent_only_recovers(self):
        fired=False
        def stop(phase,operation,path):
            nonlocal fired
            if not fired and phase=='after' and operation=='replace' and path=='receipts/requests/reject-close.json':
                fired=True
                raise self.p.storage.Refused('fixture-stop','Stop after durable intent')
        pkg=self.patch();error=self.rejected(pkg,observer=stop)
        self.assertTrue(fired)
        self.assertEqual(error['code'],'fixture-stop')
        self.assertNotIn('abandon',error['adapter_exits'])
        actions=error['adapter_exits']['recover']
        self.assertEqual(len(actions),1)
        self.assertEqual(actions[0]['request_id'],'reject-close')
        result=subprocess.run(actions[0]['command'],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(self.adapter().apply(self.ws,pkg,'reject')['ok'])
        self.assertTrue(self.u.check(scope='all')['ok'])

    def test_unverified_label_preserves_source_assertion(self):
        pkg=self.patch();pkg['understanding']=['This adapter is already safe.']
        self.adapter().apply(self.ws,pkg,'label')
        item=self.u.s.json(str(next((self.ws/'projects/meta/pending/understanding').glob('*.json')).relative_to(self.ws)))
        self.assertTrue(item['body'].startswith('Adapter-provided, unverified. Observe before adoption.\n\n'))
        self.assertTrue(item['body'].endswith(pkg['understanding'][0]))
        self.assertIn('adapter-sha256:'+self.p.storage.sha(self.p.storage.encode(pkg)),item['source_refs'])

    def test_partial_write_intent_never_offers_abandon(self):
        fired=False
        def stop(phase,operation,path):
            nonlocal fired
            if not fired and phase=='after' and operation=='replace' and path=='projects/meta/object/fixture.cfg':
                fired=True
                raise self.p.storage.Refused('fixture-stop','Stop after actual target write')
        pkg=self.patch();error=self.rejected(pkg,observer=stop)
        self.assertTrue(fired)
        self.assertTrue((self.ws/'projects/meta/object/fixture.cfg').exists())
        self.assertNotIn('abandon',error['adapter_exits'])
        self.assertEqual(error['adapter_exits']['state'],'recover-intent')
        self.assertTrue(self.adapter().apply(self.ws,pkg,'reject')['ok'])
        self.assertTrue(self.u.check(scope='all')['ok'])

    def test_abandon_does_not_bypass_frozen_input_corruption(self):
        extra=self.ws/'projects/meta/object/skills/unit-extra';extra.mkdir()
        error=self.rejected(self.patch())
        current=self.ws/'projects/meta/task/current.md';original=current.read_bytes()
        current.write_bytes(original+b'UNAUTHORIZED EDIT')
        action=error['adapter_exits']['abandon']
        result=subprocess.run(action['command'],input=json.dumps(action['input']),text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,1)
        self.assertEqual(json.loads(result.stdout)['code'],'stale')
        self.assertIsNotNone(self.u.manifest()['projects']['meta']['active'])
        current.write_bytes(original)
        self.execute_abandon(error)
        self.assertEqual(len(list((self.ws/'projects/meta/pending/target').glob('*.json'))),1)

    def test_combined_label_limit_rejected_before_intake(self):
        pkg=self.patch();pkg['understanding']=['x'*self.p.layout.MAX_TEXT]
        error=self.rejected(pkg)
        self.assertEqual(error['code'],'size')
        self.no_intake()

    def test_missing_skills_reports_required_members(self):
        skills=self.ws/'projects/meta/object/skills'
        skills.rename(Path(self.temp.name)/'saved-skills')
        result=self.u.check(scope='project',project='meta')
        issue=next(i for i in result['issues'] if i['code']=='object')
        self.assertEqual(set(issue['missing']),{'projects/meta/object/skills/unit-'+v+'/SKILL.md' for v in self.p.layout.VIEWS})
        self.assertFalse(any(i['code']=='filesystem' for i in result['issues']))


if __name__=='__main__':unittest.main(verbosity=2)
