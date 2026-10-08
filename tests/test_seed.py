"""Original r3 installed-source contract, not cloning a personalized instance."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
spec=importlib.util.spec_from_file_location('fixtures',Path(__file__).with_name('test_unit.py'))
t=importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


def pins(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def tree_identity(root):
    return {str(p.relative_to(root)):(p.lstat().st_mode,p.lstat().st_mtime_ns,
            hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() and not p.is_symlink() else None)
            for p in [root,*root.rglob('*')]}


class SeedTests(unittest.TestCase):
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

    def test_target_inside_source_refuses_without_any_tree_change(self):
        root=Path(self.temp.name);before=tree_identity(root)
        result=t.INSTALL.install(self.ws/'nested',source=self.ws)
        self.assertEqual(result.get('code'),'source-target-overlap',result)
        self.assertEqual(tree_identity(root),before)
        self.assertNotIn('staging',result)

    def test_source_inside_target_and_equal_refuse_before_staging(self):
        root=Path(self.temp.name);before=tree_identity(root)
        for destination in (root,self.ws):
            with self.subTest(destination=destination):
                result=t.INSTALL.install(destination,source=self.ws)
                self.assertEqual(result.get('code'),'source-target-overlap',result)
                self.assertNotIn('staging',result)
                self.assertEqual(tree_identity(root),before)

    def test_canonical_parent_and_source_alias_cannot_hide_overlap(self):
        root=Path(self.temp.name);alias=root/'source-alias';alias.symlink_to(self.ws,target_is_directory=True)
        before=tree_identity(root)
        result=t.INSTALL.install(alias/'nested',source=alias)
        self.assertEqual(result.get('code'),'source-target-overlap',result)
        self.assertEqual(tree_identity(root),before)
        self.assertNotIn('staging',result)

    def test_name_prefix_is_not_ancestry(self):
        before=tree_identity(self.ws);dest=self.ws.with_name(self.ws.name+'-other')
        result=t.INSTALL.install(dest,source=self.ws)
        self.assertTrue(result['ok'],result)
        self.assertEqual(tree_identity(self.ws),before)

    def test_installed_source_expands_neutral_without_private_state(self):
        project=self.project()
        self.start(project)
        marker=b'PRIVATE-SOURCE-MUST-NOT-EXPORT'
        self.work(project,'private.txt',marker)
        self.pending(body=marker.decode())
        for name in ('focus.md','projects/meta/understanding/description.md',
                     'projects/meta/tools/adapter.py','projects/meta/object/assets/private.txt'):
            p=self.ws/name
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(marker)
        before=pins(self.ws)
        dest=Path(self.temp.name)/'neutral'
        answer=t.INSTALL.install(dest,source=self.ws)
        self.assertTrue(answer['ok'],answer)
        self.assertEqual(pins(self.ws),before)
        for p in dest.rglob('*'):
            if p.is_file():
                self.assertNotIn(marker,p.read_bytes(),str(p))
        reference=Path(self.temp.name)/'reference'
        self.assertTrue(t.INSTALL.install(reference)['ok'])
        self.assertEqual(pins(dest),pins(reference))

    def test_adopted_changed_generic_source_refuses_before_target_effects(self):
        path=self.ws/'projects/meta/object/rules.md'
        item,task=self.start()
        self.work('meta','rules',path.read_bytes()+b'\nInstance-only revision.\n')
        self.assertTrue(self.close(item,task,writes=[dict(path='object/rules.md',from_work='rules')])['ok'])
        self.assertTrue(self.u.check(scope='all')['ok'])
        before=pins(self.ws)
        dest=Path(self.temp.name)/'rejected'
        result=t.INSTALL.install(dest,source=self.ws)
        self.assertFalse(result['ok'])
        self.assertEqual(result['code'],'source-evolved')
        self.assertFalse(dest.exists())
        self.assertNotIn('staging',result)
        self.assertEqual(pins(self.ws),before)

    def test_shared_byte_drift_refuses_even_if_manifest_was_not_updated(self):
        (self.ws/'projects/meta/object/rules.md').write_bytes(b'Unadopted drift')
        dest=Path(self.temp.name)/'rejected'
        result=t.INSTALL.install(dest,source=self.ws)
        self.assertFalse(result['ok'])
        self.assertEqual(result['code'],'source-drift')
        self.assertFalse(dest.exists())
        self.assertNotIn('staging',result)

    def test_cli_exposes_explicit_source_without_loading_its_tools(self):
        (self.ws/'projects/meta/tools/adapter.py').write_text('raise RuntimeError("MUST NOT EXECUTE")',encoding='utf-8')
        dest=Path(self.temp.name)/'via-cli'
        result=subprocess.run([sys.executable,'-I','-S','-B',str(t.SOURCE/'install.py'),
            str(dest),'--source',str(self.ws)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])
        self.assertNotIn('MUST NOT EXECUTE',(dest/'projects/meta/tools/adapter.py').read_text(encoding='utf-8'))

    def test_instance_loader_is_inspected_not_executed(self):
        (self.ws/'projects/meta/object/mcp/loader.py').write_text('raise RuntimeError("UNTRUSTED LOADER")',encoding='utf-8')
        dest=Path(self.temp.name)/'rejected'
        result=t.INSTALL.install(dest,source=self.ws)
        self.assertEqual(result.get('code'),'source-drift',result)
        self.assertFalse(dest.exists())
        self.assertNotIn('UNTRUSTED LOADER',result.get('detail',''))

    def test_different_seed_baseline_is_not_silently_upgraded(self):
        path=self.ws/'manifest.json'
        m=json.loads(path.read_text(encoding='utf-8'))
        m['upstream']['projects/meta/object/rules.md']='0'*64
        path.write_text(json.dumps(m),encoding='utf-8')
        before=pins(self.ws)
        dest=Path(self.temp.name)/'rejected'
        result=t.INSTALL.install(dest,source=self.ws)
        self.assertEqual(result.get('code'),'source-version',result)
        self.assertFalse(dest.exists())
        self.assertEqual(pins(self.ws),before)


if __name__=='__main__':
    unittest.main(verbosity=2)
