"""Real bounded child-process SIGKILL tests, not simulated successful receipts."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import random
import time
import unittest
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('unit_tests',Path(__file__).with_name('test_unit.py'))
t=importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


def worker():
    mode,workspace,request,cut=sys.argv[2:6]
    payload=json.loads(Path(request).read_text(encoding='utf-8'))
    count=0
    def event(phase,operation,path):
        nonlocal count
        count+=1
        print(json.dumps(dict(checkpoint=count,phase=phase,operation=operation,path=path)),flush=True)
        if count==int(cut):
            os.kill(os.getpid(),signal.SIGKILL)
    if mode=='install':
        result=t.INSTALL.install(workspace,observer=event)
    elif mode=='adapter':
        adapter=t.module('worker_adapter',Path(workspace)/'projects/meta/tools/adapter.py')
        result=adapter.apply(workspace,payload,'crash-adapter',observer=event)
    else:
        cli=t.module('worker_cli',Path(workspace)/'projects/meta/object/mcp/cli.py')
        p=cli.load_kernel(workspace)
        unit=p.mechanics.Unit(workspace,event)
        result=unit.call(payload['operation'],payload['arguments'])
    print(json.dumps(dict(result=result,checkpoints=count)),flush=True)
    return 0 if result.get('ok') else 1


class RecoveryTests(unittest.TestCase):
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

    def child(self,mode,ws,payload,cut):
        request=Path(self.temp.name)/'child-input.json'
        request.write_text(json.dumps(payload),encoding='utf-8')
        return subprocess.run([sys.executable,'-I','-S','-B',str(Path(__file__).resolve()),
                               'worker',mode,str(ws),str(request),str(cut)],capture_output=True,text=True,timeout=20)

    def matrix(self,operation,arguments,assert_result):
        probe=Path(self.temp.name)/'probe'
        shutil.copytree(self.ws,probe)
        payload=dict(operation=operation,arguments=arguments)
        result=self.child('call',probe,payload,0)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout[-1000:])
        count=json.loads(result.stdout.splitlines()[-1])['checkpoints']
        self.assertGreater(count,0)
        for cut in range(1,count+1):
            trial=Path(self.temp.name)/('cut-'+str(cut))
            shutil.copytree(self.ws,trial)
            killed=self.child('call',trial,payload,cut)
            self.assertEqual(killed.returncode,-signal.SIGKILL,(cut,killed.stderr))
            cli=t.module('recovery_cli',trial/'projects/meta/object/mcp/cli.py')
            p=cli.load_kernel(trial)
            unit=p.mechanics.Unit(trial)
            r=unit.receipt(arguments['request_id'])
            if r and r['state']=='pending':
                # Current code cannot steal the frozen incomplete operation.
                old=t.module('old_cli',trial/'receipts/engines'/r['engine']/'cli.py')
                oldp=old.load_kernel(trial)
                answer=oldp.mechanics.Unit(trial).recover(arguments['request_id'])
            else:
                answer=unit.call(operation,arguments)
            self.assertTrue(answer['ok'],(cut,answer))
            self.assertEqual(answer,unit.call(operation,arguments))
            self.assertTrue(unit.check(scope='all')['ok'],(cut,unit.check(scope='all')))
            assert_result(trial,answer,cut)
        print('SIGKILL',operation,count,'boundaries checked',flush=True)

    def test_pending_intake_every_checkpoint(self):
        args=dict(project='meta',kind='target',source_refs=['isolated-test'],body='MARKER-PENDING-XYZ',request_id='crash-intake')
        def inspect(trial,answer,cut):
            self.assertEqual(len(list((trial/'projects/meta/pending/target').glob('*.json'))),1)
            for f in (trial/'receipts').rglob('*'):
                if f.is_file():
                    self.assertNotIn(b'MARKER-PENDING-XYZ',f.read_bytes(),(cut,str(f)))
        self.matrix('pending_add',args,inspect)

    def test_task_close_every_checkpoint(self):
        project=self.project()
        item,task=self.start(project)
        self.work(project,'out',b'MARKER-WORK-XYZ')
        args=self.closeargs(item,task,request_id='crash-close',writes=[dict(path='object/result',from_work='out')],
            new_pending=[dict(project='meta',kind='understanding',source_refs=['test'],body='recognition from result')])
        def inspect(trial,answer,cut):
            self.assertEqual((trial/'projects'/project/'object/result').read_bytes(),b'MARKER-WORK-XYZ')
            self.assertTrue((trial/answer['archive']/'work/out').exists())
            self.assertEqual(len(list((trial/'archive'/project).iterdir())),1)
            for f in (trial/'receipts').rglob('*'):
                if f.is_file():
                    self.assertNotIn(b'MARKER-WORK-XYZ',f.read_bytes(),(cut,str(f)))
                    self.assertNotIn(b'TUFSS0VSLVdPUkstWFla',f.read_bytes(),(cut,str(f)))
        self.matrix('task_close',args,inspect)

    def test_installer_every_checkpoint_not_half_published(self):
        probe=Path(self.temp.name)/'install-probe'
        result=self.child('install',probe,{},0)
        self.assertEqual(result.returncode,0,result.stderr)
        count=json.loads(result.stdout.splitlines()[-1])['checkpoints']
        for cut in range(1,count+1):
            target=Path(self.temp.name)/('install-'+str(cut))
            killed=self.child('install',target,{},cut)
            self.assertEqual(killed.returncode,-signal.SIGKILL,(cut,killed.stderr))
            if target.exists():
                cli=t.module('installed_cli',target/'projects/meta/object/mcp/cli.py')
                p=cli.load_kernel(target)
                self.assertTrue(p.mechanics.Unit(target).check(scope='all')['ok'],cut)
        print('SIGKILL install',count,'boundaries checked',flush=True)

    def test_adapter_every_checkpoint(self):
        pkg=t.UnitTests.patch(self)
        probe=Path(self.temp.name)/'adapter-probe'
        shutil.copytree(self.ws,probe)
        normal=self.child('adapter',probe,pkg,0)
        self.assertEqual(normal.returncode,0,normal.stderr+normal.stdout[-1000:])
        count=json.loads(normal.stdout.splitlines()[-1])['checkpoints']
        for cut in range(1,count+1):
            trial=Path(self.temp.name)/('adapter-'+str(cut))
            shutil.copytree(self.ws,trial)
            killed=self.child('adapter',trial,pkg,cut)
            self.assertEqual(killed.returncode,-signal.SIGKILL,(cut,killed.stderr))
            adapter=t.module('resume_adapter',trial/'projects/meta/tools/adapter.py')
            result=adapter.apply(trial,pkg,'crash-adapter')
            self.assertTrue(result['ok'],(cut,result))
            self.assertEqual(result,adapter.apply(trial,pkg,'crash-adapter'))
            self.assertEqual((trial/'projects/meta/object/fixture.cfg').read_bytes(),b'config')
            self.assertEqual(len(list((trial/'projects/meta/pending/understanding').glob('*.json'))),1)
            self.assertEqual(len(list((trial/'archive/meta').iterdir())),1)
        print('SIGKILL adapter',count,'boundaries checked',flush=True)

    def test_independent_time_sample_installs(self):
        # Stop from a parent timer, not from the installer's checkpoint counter.
        rng=random.Random(271828)
        killed=0
        request=Path(self.temp.name)/'timed-input.json'
        request.write_text('{}',encoding='utf-8')
        for i in range(12):
            target=Path(self.temp.name)/('timed-'+str(i))
            proc=subprocess.Popen([sys.executable,'-I','-S','-B',str(Path(__file__).resolve()),
                'worker','install',str(target),str(request),'0'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            time.sleep(rng.uniform(.015,.085))
            if proc.poll() is None:
                proc.kill()
            out,err=proc.communicate(timeout=10)
            self.assertIn(proc.returncode,(0,-signal.SIGKILL),err)
            killed+=proc.returncode==-signal.SIGKILL
            if target.exists():
                cli=t.module('timed_cli',target/'projects/meta/object/mcp/cli.py')
                p=cli.load_kernel(target)
                self.assertTrue(p.mechanics.Unit(target).check(scope='all')['ok'],(i,out[-1000:]))
        self.assertGreater(killed,0)
        print('Independent timed install samples: 12; SIGKILL observed:',killed,flush=True)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='worker':
        raise SystemExit(worker())
    unittest.main(verbosity=2)
