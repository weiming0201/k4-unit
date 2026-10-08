"""Measure actual compact storage in three declared inert fixture cases."""
import importlib.util
import json
from pathlib import Path
import sys
spec=importlib.util.spec_from_file_location('storage_fixtures',Path(__file__).with_name('test_unit.py'))
t=importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


def stats(case):
    receipts=case.ws/'receipts'
    files=sorted((receipts/'requests').glob('*.json'))
    sizes={p.stem:p.stat().st_size for p in files}
    operations={}
    for p in files:
        item=json.loads(p.read_text(encoding='utf-8'))
        assert item['state']=='complete' and 'steps' not in item
        operations.setdefault(item['operation'],[]).append(p.stat().st_size)
    snapshots=[p for p in (receipts/'engines').iterdir() if p.is_dir()]
    staging=[str(p.relative_to(receipts)) for p in (receipts/'staging').rglob('*') if p.is_file() and p.name!='.gitkeep']
    assert not staging,staging
    return dict(completed_receipt_count=len(files),completed_receipt_bytes=sum(sizes.values()),
        receipt_byte_ranges={op:dict(count=len(values),minimum=min(values),maximum=max(values),total=sum(values))
                             for op,values in operations.items()},
        kernel_snapshots=len(snapshots),kernel_snapshot_bytes=sum(p.stat().st_size for s in snapshots for p in s.rglob('*') if p.is_file()),
        manifest_bytes=(case.ws/'manifest.json').stat().st_size,
        archive_bytes=sum(p.stat().st_size for p in (case.ws/'archive').rglob('*') if p.is_file()),
        pending_transaction_count=len(case.u.incomplete()),staging_residue=staging)


def measure(name):
    case=t.UnitTests('test_neutral_install_and_scopes')
    case.setUp()
    try:
        project=case.project()
        if name=='selected-item-boundary':
            items=[case.pending(project,body='Inert selected item '+str(i)) for i in range(case.p.layout.MAX_ITEMS)]
            task=case.call('task_start',project=project,
                selected=[{k:item[k] for k in ('id','kind','sha256')} for item in items],
                task='Read-only 128-item capacity fixture. Acceptance: all selected items disposed and empty active slot.',write_scopes=[])
            outcome=case.call('task_close',project=project,task_id=task['task_id'],baseline=task['baseline'],
                outcome='completed',dispositions={item['id']:'done' for item in items},
                checks=['Inert fixture checks'],transcript_refs=[])
            inputs=dict(selected_items=len(items),write_bytes=0)
        else:
            item,task=case.start(project)
            count=case.p.layout.MAX_FILE if name=='single-file-boundary' else 128
            body=b'x'*count
            case.work(project,'output',body)
            outcome=case.close(item,task,writes=[dict(path='object/result',from_work='output')])
            assert (case.ws/'projects'/project/'object/result').read_bytes()==body
            inputs=dict(selected_items=1,write_bytes=count)
        assert outcome['ok'] and case.u.check(scope='all')['ok']
        assert case.u.manifest()['projects'][project]['active'] is None
        return dict(case=name,inputs=inputs,storage=stats(case))
    finally:
        case.doCleanups()


if __name__=='__main__':
    print(json.dumps(dict(python=sys.version,platform=sys.platform,
        scope='Measured post-close bytes, not runtime memory, disk allocation blocks, or a global worst case.',
        results=[measure(n) for n in ('typical','single-file-boundary','selected-item-boundary')]),indent=2))
