"""Apply one authorized, declarative, local adapter through the Unit task kernel.

No shell hooks, downloads, model calls or external configuration writes. The
operator supplies authority; hashes and application checks do not create it.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
UNVERIFIED = 'Adapter-provided, unverified. Observe before adoption.\n\n'


def load(workspace, engine=None):
    root=Path(workspace).absolute()
    directory=root/'projects/meta/object/mcp' if engine is None else root/'receipts/engines'/engine
    spec=importlib.util.spec_from_file_location('_unit_adapter_cli',directory/'cli.py')
    cli=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return cli.load_kernel(root)


def apply(workspace, package, request_id, observer=None):
    p=load(workspace)
    try:
        return apply_bound(p,workspace,package,request_id,observer)
    except Exception as error:
        # Diagnostics are read-only and cannot replace the primary failure.
        if hasattr(error,'extra'):
            try:
                error.extra['adapter_exits']=refusal_exits(p,workspace,request_id)
            except Exception as diagnostic:
                error.extra['adapter_exits']=dict(state='unknown',detail=str(diagnostic),
                    note='Inspect receipts; no automatic release or claim of a safe cancellation.')
        raise


def refusal_exits(p,workspace,request_id):
    """Expose executable old-bound exits without choosing or executing one."""
    p.storage.key(request_id)
    unit=p.mechanics.Unit(workspace)
    with unit.s.lock():
        pending=unit.incomplete()
        if pending:
            return dict(state='recover-intent',recover=[dict(request_id=i,command=unit.recovery(v['engine'],i))
                for i,v in pending],note='Recover durable intent first; cancellation is not available.')
        closed=unit.receipt(request_id+'-close')
        if closed and closed['state']=='complete':
            return dict(state='completed',result=closed['result'],note='Replay original request to obtain its result.')
        started=unit.receipt(request_id+'-start')
        if not started:
            return dict(state='not-started',note='No task was started by this request. Any admitted candidate remains pending.')
        m=unit.manifest();active=m['projects']['meta']['active'];result=started['result']
        if not active or active['id']!=result['task_id']:
            return dict(state='no-longer-active',note='Do not reuse this adapter request; inspect its prior closure before a new request.')
        abandon_id=request_id+'-abandon'
        return dict(state='active-refused',retry=dict(request_id=request_id,
                note='Remove only an authorized removable obstacle, then replay the exact original package and request.'),
            abandon=dict(command=unit.recovery(result['engine'])+['call','task_close','--input','-'],
                input=dict(project='meta',task_id=result['task_id'],baseline=result['baseline'],outcome='incomplete',
                    dispositions={v['id']:'remaining' for v in active['selected']},checks=[
                        'Explicitly abandon this refused adapter; no requested implementation is claimed done.'],
                    transcript_refs=[],request_id=abandon_id),
                note='Explicit choice only. On success keep remaining candidate; submit corrected package under a new request ID. '
                     'Frozen inputs and all existing close guards still apply; this is not force-close.'))


def apply_bound(p,workspace,package,request_id,observer):
    S=p.storage
    require=p.mechanics.require
    # Bound identities are deterministic phases of ONE installation request.
    S.key(request_id)
    require(len(request_id)<=48,'identifier','Adapter request ID is at most 48 characters')
    require(isinstance(package,dict) and set(package)=={'description','source_refs','patch','understanding'},
            'adapter','Expected description, source_refs, patch and understanding')
    S.text(package['description']);p.mechanics.sources(package['source_refs'])
    patch=package['patch']
    require(isinstance(patch,list) and 0<len(patch)<=p.layout.MAX_ITEMS,'adapter','Expected a finite nonempty patch')
    seen=set()
    for w in patch:
        require(isinstance(w,dict) and set(w)=={'path','before','content'},'adapter','Patch requires path/before/content')
        path=S.rel(w['path'])
        require(path not in seen and path.split('/')[0] in ('object','tools'),
                'adapter-scope','Adapter writes only meta object/tools',path)
        seen.add(path)
        require(w['before'] is None or (isinstance(w['before'],str) and len(w['before'])==64
                and all(c in '0123456789abcdef' for c in w['before'])),'adapter','Invalid expected digest',path)
        if w['content'] is not None:
            S.unblob(w['content'])
        else:
            require(w['before'] is not None,'adapter','Delete needs an existing baseline',path)
    recognition=package['understanding']
    require(isinstance(recognition,list) and 0<len(recognition)<=p.layout.MAX_ITEMS,
            'adapter','Provide recognition questions; do not write understanding directly')
    recognition=[UNVERIFIED+S.text(v) for v in recognition]
    for v in recognition:S.text(v)
    # Generated source/task text has the same limits as direct kernel input.
    recognition_sources=package['source_refs']+['adapter-sha256:'+S.sha(S.encode(package))]
    p.mechanics.sources(recognition_sources)
    task='Apply authorized adapter: '+package['description']+'\nAcceptance: exact declared patch and sourced recognition requests; no model or host effects.'
    S.text(task)
    encoded=S.encode(package)
    require(len(encoded)<=p.layout.MAX_FILE//2,'size','Adapter bundle too large for one pending item')
    unit=p.mechanics.Unit(workspace,observer)
    phases={n:request_id+'-'+n for n in ('intake','start','close')}
    intake_args=dict(project='meta',kind='target',source_refs=package['source_refs'],
        body=package['description'],files={'adapter.json':S.blob(encoded)},request_id=phases['intake'])
    # Refuse changed replay input before any work file can be overwritten.
    old=unit.receipt(phases['intake'])
    require(old is None or old['input_sha']==S.sha(S.encode(intake_args)),
            'request-conflict','Adapter request identity already has different content')
    closed=unit.receipt(phases['close'])
    if closed:
        if closed['state']=='complete':
            return closed['result']
        oldp=load(workspace,closed['engine'])
        return oldp.mechanics.Unit(workspace,observer).recover(phases['close'])
    # Every interrupted phase has its own frozen recovery entry. Never create
    # a replacement ID merely because the prior attempt was interrupted.
    for n in ('intake','start'):
        r=unit.receipt(phases[n])
        if r and r['state']=='pending':
            oldp=load(workspace,r['engine'])
            oldp.mechanics.Unit(workspace,observer).recover(phases[n])
    if unit.receipt(phases['start']) is None:
        # Determinate package refusal precedes intake. Environmental checks are
        # still repeated under the kernel's close lock, including CAS.
        with unit.s.lock():
            m=unit.manifest()
            other=[dict(project=n,task_id=e['active']['id'],engine=e['active']['engine'])
                   for n,e in m['projects'].items() if n!='meta' and e['active'] is not None]
            prefix='object/skills/'
            p.mechanics.validate_skill_names({w['path'][len(prefix):].split('/')[0]
                for w in patch if w['path'].startswith(prefix)})
            for w in patch:
                p.mechanics.validate_structure_patch(w['path'],None if w['content'] is None else S.unblob(w['content']),other)
    item=unit.call('pending_add',intake_args)
    bound=unit.receipt(phases['start'])
    if bound is None:
        # Stale patch leaves its candidate pending but performs no object write.
        for w in patch:
            require(unit.s.digest('projects/meta/'+w['path'])==w['before'],'adapter-stale','Adapter baseline changed',w['path'])
    start_args=dict(project='meta',selected=[{k:item[k] for k in ('id','kind','sha256')}],
        task=task,
        write_scopes=sorted(seen),request_id=phases['start'])
    started=unit.call('task_start',start_args)
    if started['engine']!=p.mechanics.ENGINE['digest']:
        p=load(workspace,started['engine']);S=p.storage
        unit=p.mechanics.Unit(workspace,observer)
    active=unit.manifest()['projects']['meta']['active']
    require(active and active['id']==started['task_id'],'adapter-task','Adapter task no longer active')
    writes=[]
    with unit.s.lock():
        for i,w in enumerate(patch):
            require(active['baseline'].get(w['path'])==w['before'],'adapter-stale','Start baseline does not match adapter',w['path'])
            src=None
            if w['content'] is not None:
                src='adapter/'+str(i)+'.payload'
                target='projects/meta/task/work/'+src
                body=S.unblob(w['content'])
                current=unit.s.digest(target)
                require(current in (None,S.sha(body)),'adapter-work-conflict','Do not overwrite changed work payload',target)
                if current is None:
                    unit.s.write(target,body,'projects/meta/task/work/adapter.tmp')
            writes.append(dict(path=w['path'],from_work=src))
    result=unit.call('task_close',dict(project='meta',task_id=started['task_id'],baseline=started['baseline'],
        outcome='completed',dispositions={item['id']:'done'},checks=['Declarative patch paths/baselines and payloads checked; package source and authorization remain operator responsibilities.'],
        transcript_refs=[],request_id=phases['close'],writes=writes,
        new_pending=[dict(project='meta',kind='understanding',body=v,
            source_refs=recognition_sources) for v in recognition]))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True)
    parser.add_argument('--package',required=True)
    parser.add_argument('--request',required=True)
    args=parser.parse_args()
    try:
        with open(args.package,'rb') as f:
            data=f.read(4*1024*1024+1)
        if len(data)>4*1024*1024:
            raise ValueError('adapter package exceeds limit')
        result=apply(args.workspace,json.loads(data.decode('utf-8')),args.request)
    except Exception as e:
        result=e.report() if hasattr(e,'report') else dict(ok=False,code='adapter-input',detail=str(e))
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0 if result.get('ok') else 1


if __name__=='__main__':
    raise SystemExit(main())
