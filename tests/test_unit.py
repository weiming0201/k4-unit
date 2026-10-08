"""Isolated developer tests; no model, registered harness or external service."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.dont_write_bytecode=True
SOURCE=Path(__file__).resolve().parents[1]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


INSTALL=module('install_test',SOURCE/'install.py')


class UnitTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='unit-four-groups-')
        self.addCleanup(self.temp.cleanup)
        self.ws=Path(self.temp.name)/'ws'
        result=INSTALL.install(self.ws)
        self.assertTrue(result['ok'],result)
        self.reload()
        self.seq=0

    def reload(self):
        cli=module('cli_test',self.ws/'projects/meta/object/mcp/cli.py')
        self.p=cli.load_kernel(self.ws)
        self.u=self.p.mechanics.Unit(self.ws)

    def request(self):
        self.seq+=1
        return 'r'+str(self.seq)

    def call(self,name,**args):
        if name!='check':
            args.setdefault('request_id',self.request())
        return self.u.call(name,args)

    def project(self):
        return self.call('project_create',title='Fixture',description='Isolated deterministic test')['project']

    def pending(self,project='meta',kind='target',body='Test a bounded change'):
        return self.call('pending_add',project=project,kind=kind,source_refs=['test fixture'],body=body)

    def start(self,project='meta',scopes=None,pending=None):
        item=pending or self.pending(project)
        args=dict(project=project,selected=[{k:item[k] for k in ('id','kind','sha256')}],
                  task='Purpose: test. Acceptance: explicit fixture result. Prediction: declared write only.',
                  write_scopes=scopes if scopes is not None else ['object'])
        return item,self.call('task_start',**args)

    def closeargs(self,item,started,**extra):
        return dict(project=started['project'],task_id=started['task_id'],baseline=started['baseline'],
                    outcome='completed',dispositions={item['id']:'done'},checks=['fixture assertions'],
                    transcript_refs=[],**extra)

    def close(self,item,started,**extra):
        return self.call('task_close',**self.closeargs(item,started,**extra))

    def work(self,project,name,body):
        p=self.ws/'projects'/project/'task/work'/name
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(body)
        return p

    def refuses(self,code,callback):
        with self.assertRaises(self.p.storage.Refused) as cm:
            callback()
        self.assertEqual(cm.exception.code,code)

    def test_neutral_install_and_scopes(self):
        self.assertTrue(self.call('check',scope='all')['ok'])
        self.assertFalse((self.ws/'AGENTS.md').exists())
        self.assertFalse((self.ws/'projects/meta/object/assets').exists())
        self.assertTrue((self.ws/'projects/meta/tools/adapter.py').is_file())
        seen=[]
        original=self.u.s.read
        def observed(path,*args,**kwargs):
            seen.append(path)
            return original(path,*args,**kwargs)
        self.u.s.read=observed
        self.assertTrue(self.call('check',scope='workspace')['ok'])
        self.assertFalse([p for p in seen if p.startswith('projects/')],seen)

    def test_repeat_install_refuses_without_mutation(self):
        before=self.u.s.tree('projects')
        result=INSTALL.install(self.ws)
        self.assertFalse(result['ok'])
        self.assertEqual(before,self.u.s.tree('projects'))

    def test_cli_isolated_and_foreign_same_name_ignored(self):
        evil=Path(self.temp.name)/'mechanics.py'
        evil.write_text('raise RuntimeError("FOREIGN MODULE EXECUTED")',encoding='utf-8')
        cli=self.ws/'projects/meta/object/mcp/cli.py'
        result=subprocess.run([sys.executable,'-I','-S','-B',str(cli),'--workspace',str(self.ws),
                               'check','--scope','all'],cwd=self.temp.name,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertTrue(json.loads(result.stdout)['ok'])

    def test_pending_replay_and_conflict(self):
        args=dict(project='meta',kind='target',source_refs=['fixture'],body='original',request_id='fixed')
        first=self.u.call('pending_add',args)
        self.assertEqual(first,self.u.call('pending_add',dict(reversed(list(args.items())))))
        self.refuses('request-conflict',lambda:self.u.call('pending_add',dict(args,body='changed')))

    def test_one_active_project_but_two_projects_independent(self):
        project=self.project()
        item,task=self.start()
        self.start(project)
        self.refuses('active-task',lambda:self.start())
        self.assertTrue(self.call('check',scope='all')['ok'])

    def test_empty_and_stale_selection(self):
        self.refuses('selection',lambda:self.call('task_start',project='meta',selected=[],task='x',write_scopes=[]))
        item=self.pending()
        item['sha256']='0'*64
        self.refuses('stale',lambda:self.start(pending=item))

    def test_close_writes_binary_archives_and_compacts(self):
        project=self.project()
        item,task=self.start(project)
        marker=b'SECRET-FIXTURE-91265\x00\xff'
        self.work(project,'demo.bin',marker)
        result=self.close(item,task,writes=[dict(path='object/demo.bin',from_work='demo.bin')])
        self.assertEqual((self.ws/'projects'/project/'object/demo.bin').read_bytes(),marker)
        self.assertEqual((self.ws/result['archive']/'work/demo.bin').read_bytes(),marker)
        self.assertEqual({p.name for p in (self.ws/'projects'/project/'task/work').iterdir()},{'.gitkeep'})
        for p in (self.ws/'receipts').rglob('*'):
            if p.is_file():
                self.assertNotIn(base64.b64encode(marker),p.read_bytes(),str(p))
                self.assertNotIn(marker,p.read_bytes(),str(p))
        self.assertTrue(self.call('check',scope='all')['ok'])

    def test_new_arrivals_and_incomplete_not_lost(self):
        item,task=self.start(scopes=[])
        new=self.pending()
        args=self.closeargs(item,task)
        args.update(outcome='incomplete',dispositions={item['id']:'remaining'})
        self.call('task_close',**args)
        for v in (item,new):
            self.assertTrue((self.ws/'projects/meta/pending/target'/(v['id']+'.json')).exists())
        self.assertTrue(self.call('check',scope='all')['ok'])

    def test_cannot_claim_completed_with_remaining(self):
        item,task=self.start(scopes=[])
        args=self.closeargs(item,task)
        args['dispositions']={item['id']:'remaining'}
        self.refuses('incomplete',lambda:self.call('task_close',**args))

    def test_current_frozen_and_stale_write_rejected(self):
        project=self.project()
        item,task=self.start(project)
        self.work(project,'out',b'new')
        target=self.ws/'projects'/project/'object/new'
        target.write_bytes(b'foreign')
        self.refuses('stale',lambda:self.close(item,task,writes=[dict(path='object/new',from_work='out')]))
        self.assertEqual(target.read_bytes(),b'foreign')
        original=(self.ws/'projects'/project/'task/current.md').read_bytes()
        (self.ws/'projects'/project/'task/current.md').write_bytes(b'changed')
        self.refuses('stale',lambda:self.close(item,task))
        (self.ws/'projects'/project/'task/current.md').write_bytes(original)

    def test_untouched_changes_do_not_conflict(self):
        project=self.project()
        item,task=self.start(project)
        (self.ws/'projects'/project/'object/other').write_bytes(b'concurrent unrelated')
        self.work(project,'out',b'own')
        self.close(item,task,writes=[dict(path='object/own',from_work='out')])
        self.assertTrue(self.call('check',scope='all')['ok'])

    def test_cross_project_pending_does_not_change_active(self):
        project=self.project()
        _,other=self.start(project)
        item,task=self.start(scopes=[])
        self.close(item,task,new_pending=[dict(project=project,kind='understanding',source_refs=['test'],body='new observation')])
        self.assertEqual(self.u.manifest()['projects'][project]['active']['id'],other['task_id'])

    def test_archive_absence_does_not_break_current_or_replay(self):
        item,task=self.start(scopes=[])
        args=self.closeargs(item,task,request_id='close-fixed')
        result=self.u.call('task_close',args)
        (self.ws/'archive').rename(Path(self.temp.name)/'history-away')
        self.assertTrue(self.call('check',scope='all')['ok'])
        self.assertEqual(self.u.call('task_close',args),result)
        item,task=self.start(scopes=[])
        self.close(item,task)

    def test_utf8_error_has_path_and_no_project_baseline(self):
        p='projects/meta/understanding/description.md'
        (self.ws/p).write_bytes(b'\xff')
        result=self.call('check',scope='project',project='meta')
        self.assertFalse(result['ok'])
        self.assertEqual(result['issues'][0]['path'],p)
        self.assertEqual(result['baselines'],{})

    def test_symlink_and_scope_refused_before_effects(self):
        project=self.project()
        item,task=self.start(project)
        self.work(project,'data',b'payload')
        outside=Path(self.temp.name)/'outside'
        outside.mkdir()
        (self.ws/'projects'/project/'object/link').symlink_to(outside,target_is_directory=True)
        self.refuses('symlink',lambda:self.close(item,task,writes=[dict(path='object/link/out',from_work='data')]))
        self.assertFalse(any(outside.iterdir()))
        self.refuses('scope',lambda:self.close(item,task,writes=[dict(path='understanding/x',from_work='data')]))

    def test_self_adoption_updates_adopted_not_upstream(self):
        before=self.u.manifest()
        item,task=self.start()
        self.work('meta','extra',b'new stable fixture')
        self.close(item,task,writes=[dict(path='object/fixture.txt',from_work='extra')])
        after=self.u.manifest()
        self.assertEqual(before['upstream'],after['upstream'])
        self.assertNotEqual(before['adopted'],after['adopted'])
        self.assertTrue(self.call('check',scope='all')['ok'])

    def test_fifth_unit_skill_rejected(self):
        item,task=self.start()
        self.work('meta','skill',b'not a fifth perspective')
        self.refuses('reserved-skill',lambda:self.close(item,task,writes=[dict(path='object/skills/unit-extra/SKILL.md',from_work='skill')]))

    def test_structural_change_cannot_strand_other_task(self):
        self.start(self.project())
        item,task=self.start()
        changed=dict(self.p.layout.contract(),contract='incompatible')
        self.work('meta','contract',self.p.storage.encode(changed))
        self.refuses('active-old-contract',lambda:self.close(item,task,writes=[dict(path='object/workspace.json',from_work='contract')]))

    def test_resident_kernel_rejects_new_disk_until_reload(self):
        item,task=self.start()
        code=(self.ws/'projects/meta/object/mcp/mechanics.py').read_bytes()+b'\n# compatible internal change\n'
        self.work('meta','new.py',code)
        self.close(item,task,writes=[dict(path='object/mcp/mechanics.py',from_work='new.py')])
        self.refuses('engine-reload-required',lambda:self.pending())
        stale=self.call('check',scope='project',project='meta')
        self.assertFalse(stale['ok'])
        self.assertEqual(stale['issues'][0]['code'],'engine-reload-required')
        self.reload()
        self.pending()

    def test_old_other_task_explicit_snapshot_close(self):
        project=self.project()
        other,old=self.start(project,scopes=[])
        item,task=self.start()
        code=(self.ws/'projects/meta/object/mcp/mechanics.py').read_bytes()+b'\n# compatible update\n'
        self.work('meta','new',code)
        self.close(item,task,writes=[dict(path='object/mcp/mechanics.py',from_work='new')])
        self.reload()
        self.refuses('old-kernel-required',lambda:self.close(other,old))
        cli=module('snapshot_cli',self.ws/'receipts/engines'/old['engine']/'cli.py')
        frozen=cli.load_kernel(self.ws)
        result=frozen.mechanics.Unit(self.ws).call('task_close',dict(self.closeargs(other,old),request_id='old-close'))
        self.assertTrue(result['ok'])

    def test_layout_source_cannot_hide_contract_change(self):
        self.start(self.project())
        item,task=self.start()
        original=(self.ws/'projects/meta/object/mcp/layout.py').read_bytes()
        changed=original.replace(b"CONTRACT = 'unit-workspace/6'",b"CONTRACT = 'incompatible'")
        self.assertNotEqual(changed,original)
        self.work('meta','layout',changed)
        self.refuses('active-old-contract',lambda:self.close(item,task,writes=[dict(path='object/mcp/layout.py',from_work='layout')]))

    def test_declarative_layout_allows_nonstructural_change(self):
        self.start(self.project())
        item,task=self.start()
        code=(self.ws/'projects/meta/object/mcp/layout.py').read_bytes()+b'\n# documentation only\n'
        self.work('meta','layout',code)
        self.close(item,task,writes=[dict(path='object/mcp/layout.py',from_work='layout')])
        self.reload()
        self.assertTrue(self.call('check',scope='all')['ok'])

    def adapter(self):
        return module('adapter_test',self.ws/'projects/meta/tools/adapter.py')

    def patch(self):
        return dict(description='Install inert adapter fixture',source_refs=['isolated test'],patch=[
            dict(path='object/fixture.cfg',before=None,content=base64.b64encode(b'config').decode()),
            dict(path='tools/fixture.py',before=None,content=base64.b64encode(b'# inert, not executed').decode())],
            understanding=['Observe whether this fixture binding would be meaningful.'])

    def test_adapter_updates_two_faces_and_only_seeds_recognition(self):
        guide=(self.ws/'projects/meta/understanding/guide/README.md').read_bytes()
        adapter=self.adapter()
        pkg=self.patch()
        result=adapter.apply(self.ws,pkg,'adapter-test')
        self.assertTrue(result['ok'])
        self.assertEqual(result,adapter.apply(self.ws,pkg,'adapter-test'))
        self.assertEqual((self.ws/'projects/meta/object/fixture.cfg').read_bytes(),b'config')
        self.assertEqual((self.ws/'projects/meta/understanding/guide/README.md').read_bytes(),guide)
        entries=list((self.ws/'projects/meta/pending/understanding').glob('*.json'))
        self.assertEqual(len(entries),1)
        self.assertEqual(len(list((self.ws/'projects/meta/pending/target').glob('*.json'))),0)
        self.assertTrue(self.call('check',scope='all')['ok'])

    def test_adapter_changed_replay_refuses(self):
        adapter=self.adapter()
        pkg=self.patch()
        adapter.apply(self.ws,pkg,'adapter-test')
        pkg['description']='different installation'
        with self.assertRaises(ValueError) as cm:
            adapter.apply(self.ws,pkg,'adapter-test')
        self.assertIn('identity',str(cm.exception))

    def test_adapter_stale_leaves_candidate_not_half_installed(self):
        (self.ws/'projects/meta/tools/fixture.py').write_bytes(b'preexisting')
        with self.assertRaises(ValueError):
            self.adapter().apply(self.ws,self.patch(),'adapter-stale')
        self.assertFalse((self.ws/'projects/meta/object/fixture.cfg').exists())
        self.assertEqual(len(list((self.ws/'projects/meta/pending/target').glob('*.json'))),1)


if __name__=='__main__':
    unittest.main(verbosity=2)
