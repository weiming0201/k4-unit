"""Recover multi-file kernel replacement through the real frozen CLI."""
import base64
import importlib.util
import json
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import unittest
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('recovery_tests',Path(__file__).with_name('test_recovery.py'))
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
t=r.t


class SelfRecoveryTests(unittest.TestCase):
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
    child=r.RecoveryTests.child

    def replacement(self):
        base=self.ws/'projects/meta/object/mcp'
        # The final pair is valid. After only mechanics is installed, importing
        # it against the old storage must fail, so current code cannot recover.
        return {'mechanics.py':(base/'mechanics.py').read_bytes()+b'\nfrom .storage import fixture_ready\n',
                'storage.py':(base/'storage.py').read_bytes()+b'\nfixture_ready = True\n'}

    def recover_cli(self,trial,request,digest):
        cli=trial/'receipts/engines'/digest/'cli.py'
        proc=subprocess.run([sys.executable,'-I','-S','-B',str(cli),'--workspace',str(trial),
            'recover','--request',request],capture_output=True,text=True,timeout=15)
        self.assertEqual(proc.returncode,0,proc.stderr+proc.stdout)
        return json.loads(proc.stdout)

    def verify_current(self,trial):
        cli=t.module('restored_cli',trial/'projects/meta/object/mcp/cli.py')
        p=cli.load_kernel(trial)
        u=p.mechanics.Unit(trial)
        self.assertTrue(u.check(scope='all')['ok'],u.check(scope='all'))
        self.assertTrue(p.storage.fixture_ready)
        return u

    def test_kernel_replace_every_boundary_via_frozen_cli(self):
        item,task=self.start()
        replacement=self.replacement()
        for name,body in replacement.items():
            self.work('meta',name,body)
        arguments=self.closeargs(item,task,request_id='replace-kernel',
            writes=[dict(path='object/mcp/'+n,from_work=n) for n in replacement])
        payload=dict(operation='task_close',arguments=arguments)
        probe=Path(self.temp.name)/'probe'
        shutil.copytree(self.ws,probe)
        normal=self.child('call',probe,payload,0)
        self.assertEqual(normal.returncode,0,normal.stderr)
        events=[json.loads(x) for x in normal.stdout.splitlines()]
        broken=next(v['checkpoint'] for v in events[:-1] if v['phase']=='after' and v['operation']=='replace'
                    and v['path']=='projects/meta/object/mcp/mechanics.py')
        count=events[-1]['checkpoints']
        observed_broken=False
        for cut in range(1,count+1):
            trial=Path(self.temp.name)/('replace-'+str(cut))
            shutil.copytree(self.ws,trial)
            killed=self.child('call',trial,payload,cut)
            self.assertEqual(killed.returncode,-signal.SIGKILL,(cut,killed.stderr))
            if cut==broken:
                current=t.module('broken_cli',trial/'projects/meta/object/mcp/cli.py')
                with self.assertRaises(ImportError):
                    current.load_kernel(trial)
                observed_broken=True
            receipt=trial/'receipts/requests/replace-kernel.json'
            if receipt.exists():
                answer=self.recover_cli(trial,'replace-kernel',task['engine'])
            else:
                # No intent yet: no product writes could have been committed.
                cli=t.module('unchanged_cli',trial/'projects/meta/object/mcp/cli.py')
                p=cli.load_kernel(trial)
                answer=p.mechanics.Unit(trial).call('task_close',arguments)
            u=self.verify_current(trial)
            self.assertEqual(answer,u.call('task_close',arguments))
            for name,body in replacement.items():
                self.assertEqual((trial/'projects/meta/object/mcp'/name).read_bytes(),body)
            self.assertEqual(len(list((trial/'archive/meta').iterdir())),1)
        self.assertTrue(observed_broken)
        print('Self kernel replacement:',count,'SIGKILL boundaries; broken-current import reproduced and recovered',flush=True)

    def test_adapter_self_tool_and_kernel_interruption(self):
        replacement=self.replacement()
        old_adapter=(self.ws/'projects/meta/tools/adapter.py').read_bytes()
        replacement_paths={'object/mcp/'+n:b for n,b in replacement.items()}
        replacement_paths['tools/adapter.py']=old_adapter+b'\n# new wrapper after committed replacement\n'
        package=dict(description='Replace generic kernel and adapter wrapper in a disposable fixture',
            source_refs=['self-recovery fixture'],patch=[dict(path=n,before=self.u.s.digest('projects/meta/'+n),
                content=base64.b64encode(b).decode()) for n,b in replacement_paths.items()],
            understanding=['Recheck reconstruction after the compatible kernel update.'])
        probe=Path(self.temp.name)/'probe'
        shutil.copytree(self.ws,probe)
        normal=self.child('adapter',probe,package,0)
        self.assertEqual(normal.returncode,0,normal.stderr+normal.stdout[-1000:])
        events=[json.loads(x) for x in normal.stdout.splitlines()]
        # Every final-close persistent boundary, plus all writes to the wrapper.
        close_begin=next(v['checkpoint'] for v in events[:-1] if v['phase']=='after' and v['operation']=='replace'
                         and v['path']=='receipts/requests/crash-adapter-close.json')
        cuts=range(close_begin,events[-1]['checkpoints']+1)
        for cut in cuts:
            trial=Path(self.temp.name)/('adapter-self-'+str(cut))
            shutil.copytree(self.ws,trial)
            killed=self.child('adapter',trial,package,cut)
            self.assertEqual(killed.returncode,-signal.SIGKILL,(cut,killed.stderr))
            receipt=json.loads((trial/'receipts/requests/crash-adapter-close.json').read_text(encoding='utf-8'))
            answer=self.recover_cli(trial,'crash-adapter-close',receipt['engine'])
            self.verify_current(trial)
            for name,body in replacement_paths.items():
                self.assertEqual((trial/'projects/meta'/name).read_bytes(),body)
            wrapper=t.module('new_wrapper',trial/'projects/meta/tools/adapter.py')
            self.assertEqual(wrapper.apply(trial,package,'crash-adapter'),answer)
            self.assertEqual(len(list((trial/'projects/meta/pending/understanding').glob('*.json'))),1)
        print('Adapter self replacement:',len(cuts),'closure SIGKILL boundaries recovered through old kernel CLI',flush=True)


if __name__=='__main__':
    unittest.main(verbosity=2)
