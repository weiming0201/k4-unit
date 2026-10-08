"""Expand a neutral Unit workspace. Never bind a harness or run a model."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
sys.dont_write_bytecode = True


def module(source):
    spec=importlib.util.spec_from_file_location('_unit_install_loader',source/'meta/object/mcp/loader.py')
    loader=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    return loader.load(source/'meta/object/mcp')


def seed_files(layout):
    return ['object/rules.md',*['object/mcp/'+n for n in layout.ENGINE_FILES],
            *['object/skills/unit-'+n+'/SKILL.md' for n in layout.VIEWS],
            'understanding/description.md','understanding/guide/README.md','tools/adapter.py']


def source_package(source):
    """Installed source identifies a matching seed, never exports private state."""
    if not (source/'manifest.json').exists():
        return source,module(source)
    seed=Path(__file__).resolve().parent
    # Inspect the instance with distribution code; do not execute its code.
    package=module(seed)
    L,S=package.layout,package.storage
    require=package.mechanics.require
    origin=S.Store(seed/'meta')
    expected={L.META+'/'+p:S.sha(origin.read(p)) for p in seed_files(L) if p.startswith('object/')}
    expected.update({L.META+'/'+p:S.sha(b'') for p in L.PLACEHOLDERS if p.startswith('object/')})
    expected[L.PACKAGE+'/workspace.json']=S.sha(S.encode(L.contract()))
    instance=package.mechanics.Unit(source)
    with instance.s.lock():
        m=instance.manifest()
        require(m['upstream']==expected,'source-version',
                'Installed source does not match this distribution; use its original verified seed','manifest.json')
        for path,digest in expected.items():
            require(m['adopted'].get(path)==digest,'source-evolved',
                    'Shared seed was evolved; do not export it as a neutral distribution',path)
            require(instance.s.digest(path)==digest,'source-drift',
                    'Shared source bytes differ from the verified distribution',path)
    # Instance guides, tools, assets, projects, history and work are not read
    # or copied. Generic defaults come from the matching distribution.
    return seed,package


def _install(target, source=None, observer=None):
    source=Path(source or Path(__file__).resolve().parent).resolve(strict=True)
    input_source=source
    source,package=source_package(source)
    L,S=package.layout,package.storage
    raw=Path(target).absolute()
    parent=raw.parent.resolve(strict=True)
    dest=parent/raw.name
    S.rel(dest.name)
    # Keep the caller's source identity even when it selects a distribution seed.
    for read_root in {input_source,source}:
        if dest.is_relative_to(read_root) or read_root.is_relative_to(dest):
            raise S.Refused('source-target-overlap',
                'Installation source and target must be disjoint directories',str(dest),source=str(read_root))
    def target_identity():
        try:
            info=dest.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISDIR(info.st_mode) or any(dest.iterdir()):
            raise S.Refused('target','Target must be absent or an empty real directory',str(dest))
        return info.st_dev,info.st_ino
    before=target_identity()
    fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
    staging=None
    try:
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise S.Refused('parent-busy','Another cooperative install is using this parent',str(parent)) from None
        if target_identity()!=before:
            raise S.Refused('target-changed','Target changed before installation',str(dest))
        staging=Path(tempfile.mkdtemp(prefix='.'+dest.name+'-unit-',dir=parent))
        store=S.Store(staging,observer)
        for p in ('projects','receipts/requests','receipts/engines','receipts/staging'):
            store.mkdir(p)
        for p in L.PROJECT_DIRS:
            store.mkdir(L.META+'/'+p)
        for p in L.PLACEHOLDERS:
            store.write(L.META+'/'+p,b'','receipts/staging/install.tmp')
        for p in ('receipts/requests','receipts/engines','receipts/staging'):
            store.write(p+'/.gitkeep',b'','receipts/staging/install.tmp')
        files=seed_files(L)
        origin=S.Store(source/'meta')
        for p in files:
            store.write(L.META+'/'+p,origin.read(p),'receipts/staging/install.tmp')
        store.write(L.PACKAGE+'/workspace.json',S.encode(L.contract()),'receipts/staging/install.tmp')
        # A copy is a pristine seed, not a clone of the source instance's private state.
        pins={L.PACKAGE+'/'+p:h for p,h in store.tree(L.PACKAGE).items()}
        manifest=dict(schema=L.SCHEMA,contract=L.CONTRACT,release=L.RELEASE,
            host_entries={},projects={'meta':dict(title='Meta',active=None,last_closed=None)},
            upstream=pins,adopted=pins)
        store.write('manifest.json',S.encode(manifest),'receipts/staging/install.tmp')
        store.write('focus.md',b'# Focus\n\nNo project selected. Read manifest.json for the authoritative project index.\n',
                    'receipts/staging/install.tmp')
        result=package.mechanics.Unit(staging).check(scope='all')
        if not result['ok']:
            raise S.Refused('candidate-check','Expanded candidate did not validate',str(staging),check=result)
        if target_identity()!=before:
            raise S.Refused('target-changed','Target changed before atomic publication',str(dest))
        store.event('before','publish',str(dest))
        os.replace(staging,dest)
        S.Store.sync(parent)
        store.event('after','publish',str(dest))
        return dict(ok=True,workspace=str(dest),harness_bound=False)
    except Exception as e:
        result=e.report() if hasattr(e,'report') else dict(ok=False,code='install',detail=str(e))
        if staging is not None and staging.exists():
            result['staging']=str(staging)
        return result
    finally:
        os.close(fd)


def install(target, source=None, observer=None):
    try:
        return _install(target, source, observer)
    except Exception as e:
        return e.report() if hasattr(e,'report') else dict(ok=False,code='install',detail=str(e))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('target')
    p.add_argument('--source',help='Seed package or matching installed workspace; never a personalized clone')
    args=p.parse_args()
    try:
        result=install(args.target,source=args.source)
    except Exception as e:
        result=e.report() if hasattr(e,'report') else dict(ok=False,code='install',detail=str(e))
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0 if result['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
