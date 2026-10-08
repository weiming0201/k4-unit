"""Regression-map witnesses; Git is only a disposable local test fixture."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('unit_tests',Path(__file__).with_name('test_unit.py'))
t=importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


class RegressionTests(unittest.TestCase):
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

    def test_cli_startup_lock_reports_busy(self):
        with self.u.s.lock():
            p=subprocess.run([sys.executable,'-I','-S','-B',str(self.ws/'projects/meta/object/mcp/cli.py'),
                '--workspace',str(self.ws),'check'],capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,1)
        self.assertEqual(json.loads(p.stdout)['code'],'busy')

    def test_invalid_source_has_containing_pending_path(self):
        item=self.pending()
        path='projects/meta/pending/target/'+item['id']+'.json'
        value=self.u.s.json(path)
        value['source_refs']=['']
        (self.ws/path).write_text(json.dumps(value),encoding='utf-8')
        result=self.call('check',scope='project',project='meta')
        self.assertFalse(result['ok'])
        self.assertEqual(result['issues'][0]['path'],path)
        self.assertEqual(result['baselines'],{})

    def test_git_commit_clone_preserves_empty_structure_and_tools(self):
        def git(cwd,*args):
            env={k:v for k,v in os.environ.items() if not k.startswith('GIT_') and k.lower() not in
                 ('http_proxy','https_proxy','all_proxy')}
            env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_TERMINAL_PROMPT='0')
            p=subprocess.run(['git','-c','user.name=Unit fixture','-c','user.email=fixture@example.invalid',
                '-c','commit.gpgsign=false','-c','core.hooksPath='+os.devnull,*args],cwd=cwd,env=env,
                capture_output=True,text=True,timeout=20,umask=0o077)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            return p.stdout.strip()
        before={str(p.relative_to(self.ws)) for p in self.ws.rglob('*') if p.is_dir()}
        git(self.ws,'init','--quiet')
        git(self.ws,'add','--','.')
        git(self.ws,'commit','--quiet','-m','Isolated Unit fixture')
        original=git(self.ws,'rev-parse','HEAD')
        clone=Path(self.temp.name)/'cloned'
        git(self.temp.name,'clone','--quiet','--no-hardlinks','--',str(self.ws),str(clone))
        self.assertEqual(git(clone,'rev-parse','HEAD'),original)
        after={str(p.relative_to(clone)) for p in clone.rglob('*') if p.is_dir() and '.git' not in p.relative_to(clone).parts}
        self.assertEqual(before,after)
        cli=t.module('clone_cli',clone/'projects/meta/object/mcp/cli.py')
        p=cli.load_kernel(clone)
        self.assertTrue(p.mechanics.Unit(clone).check(scope='all')['ok'])
        answer=p.mechanics.Unit(clone).call('project_create',dict(title='After clone',description='Actual invocation',request_id='clone-create'))
        self.assertTrue(answer['ok'])

    def test_neutral_source_ignores_private_extras_and_matching_instance_expands(self):
        package=Path(self.temp.name)/'package'
        shutil.copytree(t.SOURCE,package)
        for name in ('focus.md','meta/task/work/private.txt','meta/pending/target/private.json','meta/object/assets/private.txt'):
            f=package/name
            f.parent.mkdir(parents=True,exist_ok=True)
            f.write_bytes(b'PRIVATE-NEVER-EXPORT-FIXTURE')
        new=Path(self.temp.name)/'neutral'
        self.assertTrue(t.INSTALL.install(new,source=package)['ok'])
        for f in new.rglob('*'):
            if f.is_file():
                self.assertNotIn(b'PRIVATE-NEVER-EXPORT-FIXTURE',f.read_bytes())
        # Installed shared bytes identify the original seed, not private state.
        expanded=Path(self.temp.name)/'from-installed'
        self.assertTrue(t.INSTALL.install(expanded,source=self.ws)['ok'])
        cli=t.module('expanded_cli',expanded/'projects/meta/object/mcp/cli.py')
        package=cli.load_kernel(expanded)
        self.assertTrue(package.mechanics.Unit(expanded).check(scope='all')['ok'])

    def test_missing_source_and_write_failure_do_not_publish(self):
        package=Path(self.temp.name)/'broken-package'
        shutil.copytree(t.SOURCE,package)
        required=package/'meta/object/rules.md'
        required.rename(package/'rules-withdrawn')
        missing=Path(self.temp.name)/'missing'
        result=t.INSTALL.install(missing,source=package)
        self.assertFalse(result['ok'])
        self.assertFalse(missing.exists())
        self.assertTrue(Path(result['staging']).is_dir())
        failed=Path(self.temp.name)/'write-failure'
        def stop(phase,operation,path):
            if phase=='before' and operation=='replace' and path.endswith('rules.md'):
                raise OSError('injected bounded fixture write failure')
        result=t.INSTALL.install(failed,observer=stop)
        self.assertFalse(result['ok'])
        self.assertFalse(failed.exists())

    def test_target_appearing_before_publish_is_not_overwritten(self):
        target=Path(self.temp.name)/'racing'
        appeared=False
        def compete(phase,operation,path):
            nonlocal appeared
            if not appeared and phase=='after' and operation=='replace' and path=='focus.md':
                target.mkdir()
                (target/'other-owner').write_bytes(b'keep')
                appeared=True
        result=t.INSTALL.install(target,observer=compete)
        self.assertFalse(result['ok'])
        self.assertEqual((target/'other-owner').read_bytes(),b'keep')
        self.assertFalse((target/'manifest.json').exists())

    def test_mixed_task_partial_selection_and_exact_replay(self):
        project=self.project()
        a=self.pending(project,'understanding')
        b=self.pending(project,'target')
        c=self.pending(project,'target')
        started=self.call('task_start',project=project,selected=[{k:v[k] for k in ('id','kind','sha256')} for v in (a,b)],
            task='Mixed local maintenance. Leave b incomplete.',write_scopes=['object','understanding'])
        self.work(project,'object',b'new object')
        self.work(project,'guide',b'new guide')
        args=dict(project=project,task_id=started['task_id'],baseline=started['baseline'],outcome='incomplete',
            dispositions={a['id']:'done',b['id']:'remaining'},checks=['a met; b not met'],transcript_refs=[],
            writes=[dict(path='object/new',from_work='object'),dict(path='understanding/guide/new.md',from_work='guide')],request_id='mixed-close')
        result=self.u.call('task_close',args)
        before={str(p.relative_to(self.ws)):p.read_bytes() for p in self.ws.rglob('*') if p.is_file()}
        self.assertEqual(self.u.call('task_close',args),result)
        self.assertEqual(before,{str(p.relative_to(self.ws)):p.read_bytes() for p in self.ws.rglob('*') if p.is_file()})
        self.assertFalse((self.ws/'projects'/project/'pending/understanding'/(a['id']+'.json')).exists())
        for v in (b,c):
            self.assertTrue((self.ws/'projects'/project/'pending/target'/(v['id']+'.json')).exists())
        self.refuses('request-conflict',lambda:self.u.call('task_close',dict(args,checks=['different'])))

    def test_metadata_bad_pin_rejected_without_baselines(self):
        m=self.u.manifest()
        m['upstream']['projects/meta/object/rules.md']='not-a-digest'
        (self.ws/'manifest.json').write_bytes(self.p.storage.encode(m))
        result=self.call('check',scope='all')
        self.assertFalse(result['ok'])
        self.assertEqual(result['baselines'],{})


if __name__=='__main__':
    unittest.main(verbosity=2)
