"""Local Unit transactions. This kernel checks structure, not truth or consent."""
from copy import deepcopy
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from . import layout as L
from .storage import Store, Refused, encode, sha, blob, unblob, key, rel, text

ENGINE = None  # Set by the loader from the exact captured module bytes.


def require(condition, code, detail, path='', **extra):
    if not condition:
        raise Refused(code, detail, path, **extra)


def sources(value, path=''):
    require(isinstance(value, list) and 0 < len(value) <= L.MAX_ITEMS,
            'sources', 'Provide a bounded nonempty list of source references', path)
    return [text(v,path) for v in value]


def object_hash(bundle):
    return sha(encode({name: sha(body) for name, body in sorted(bundle.items())}))


def declared_structure(body):
    """Read the declarative layout without executing replacement code.

    This checks declared compatibility, not arbitrary program semantics. Other
    kernel code still requires external verification before authorized adoption.
    """
    values={}
    def value(node):
        if isinstance(node,ast.Constant):
            if isinstance(node.value,int) and abs(node.value)>L.MAX_TOTAL*2:
                raise ValueError('layout constant exceeds bound')
            if isinstance(node.value,str) and len(node.value)>L.MAX_TEXT:
                raise ValueError('layout string exceeds bound')
            return node.value
        if isinstance(node,ast.Name) and node.id in values:
            return values[node.id]
        if isinstance(node,(ast.List,ast.Tuple)):
            items=[value(x) for x in node.elts]
            return items if isinstance(node,ast.List) else tuple(items)
        if isinstance(node,ast.Dict):
            return {value(k):value(v) for k,v in zip(node.keys,node.values)}
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Mult)):
            a,b=value(node.left),value(node.right)
            if isinstance(node.op,ast.Mult):
                if isinstance(a,(str,list,tuple)) and isinstance(b,int) and len(a)*max(b,0)>L.MAX_TEXT:
                    raise ValueError('layout repetition exceeds bound')
                if isinstance(b,(str,list,tuple)) and isinstance(a,int) and len(b)*max(a,0)>L.MAX_TEXT:
                    raise ValueError('layout repetition exceeds bound')
                result=a*b
            else:
                result=a+b
            if isinstance(result,int) and abs(result)>L.MAX_TOTAL*2:
                raise ValueError('layout arithmetic exceeds bound')
            return result
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='list' and len(node.args)==1 and not node.keywords:
            return list(value(node.args[0]))
        raise ValueError('layout constants and contract projection must be declarative')
    try:
        parsed=ast.parse(body.decode('utf-8'))
        projection=None
        for node in parsed.body:
            if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
                values[node.targets[0].id]=value(node.value)
            elif isinstance(node,ast.FunctionDef):
                if node.name=='contract':
                    require(len(node.body)==1 and isinstance(node.body[0],ast.Return),'contract','Projection must be a literal return')
                    projection=value(node.body[0].value)
            elif not (isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str)):
                raise ValueError('unsupported executable layout statement')
        require(projection is not None,'contract','Missing structural projection')
        return values['SCHEMA'],projection
    except (ValueError,TypeError,KeyError,SyntaxError,UnicodeError,OverflowError) as e:
        raise Refused('contract','Cannot statically inspect layout: '+str(e),'object/mcp/layout.py') from None


def validate_skill_names(names):
    reserved={'unit-'+v for v in L.VIEWS}
    require(not {n for n in names if n.startswith('unit-')} - reserved,
            'reserved-skill', 'unit- is reserved for exactly four perspectives')


def validate_structure_patch(path, body, other_tasks):
    """Shared preflight/close gate; inspect declarations, never execute payload."""
    if path == 'object/workspace.json':
        try:
            proposed=json.loads(body.decode('utf-8')) if body is not None else None
        except (ValueError,UnicodeError):
            raise Refused('contract','Invalid structural projection',path) from None
        changed=proposed!=L.contract()
    elif path == 'object/mcp/layout.py':
        declared=declared_structure(body) if body is not None else None
        changed=declared!=(L.SCHEMA,L.contract())
    else:
        return
    if changed:
        require(not other_tasks,'active-old-contract','Other tasks would be stranded by contract migration',
                projects=[v['project'] for v in other_tasks],tasks=other_tasks)
        raise Refused('migration-required','Structural migration needs a separately supported migration',path)


class Transaction:
    """Build a finite patch with all initial preconditions before persisting intent."""
    def __init__(self, store):
        self.s = store
        self.steps = []
        self.checks = {}
        self.total = 0

    def expect(self, path, digest):
        rel(path)
        require(path not in self.checks or self.checks[path] == digest,
                'precondition', 'Conflicting expected versions', path)
        self.checks[path] = digest

    def write(self, path, body, expected=None):
        require(isinstance(body, bytes) and len(body) <= L.MAX_FILE,
                'size', 'Write exceeds file limit', path)
        self.total += len(body)
        require(self.total <= L.MAX_TOTAL and len(self.steps) < L.MAX_FILES,
                'size', 'Transaction exceeds declared limit')
        self.expect(path, expected)
        self.steps.append(dict(kind='write', path=path, before=expected,
                               after=sha(body), body=blob(body)))

    def delete(self, path, expected):
        self.expect(path, expected)
        self.steps.append(dict(kind='delete', path=path, before=expected))

    def mkdir(self, path):
        rel(path)
        self.steps.append(dict(kind='mkdir', path=path))

    def move(self, src, dst, expected_tree):
        rel(src); rel(dst)
        require(not self.s.path(dst).exists(), 'conflict', 'Archive already exists', dst)
        self.steps.append(dict(kind='move', path=src, destination=dst, tree=expected_tree))

    def preflight(self):
        for path, expected in self.checks.items():
            require(self.s.digest(path) == expected, 'stale', 'File baseline changed', path)
        for step in self.steps:
            self.s.path(step['path'])
            if step['kind'] == 'mkdir':
                p = self.s.path(step['path'])
                require(not p.exists() or p.is_dir(), 'directory', 'Directory occupied', step['path'])


class Unit:
    def __init__(self, workspace, observer=None):
        require(ENGINE is not None, 'loader', 'Use the captured-byte loader')
        self.s = Store(workspace, observer)

    def manifest(self):
        m = self.s.json('manifest.json')
        require(isinstance(m, dict) and m.get('schema') == L.SCHEMA,
                'manifest', 'Unsupported manifest schema', 'manifest.json')
        require(m.get('contract') == L.CONTRACT, 'contract', 'Unsupported structural contract', 'manifest.json')
        require(isinstance(m.get('projects'), dict) and 'meta' in m['projects'],
                'manifest', 'Unique meta registry entry is required', 'manifest.json')
        require(isinstance(m.get('adopted'), dict) and isinstance(m.get('upstream'), dict)
                and isinstance(m.get('host_entries'), dict), 'manifest', 'Missing baseline/host maps', 'manifest.json')
        for name in ('adopted','upstream'):
            require(len(m[name])<=L.MAX_FILES,'manifest','Too many pinned members','manifest.json')
            for p,h in m[name].items():
                rel(p)
                require(p.startswith(L.PACKAGE+'/') and isinstance(h,str) and len(h)==64
                        and all(c in '0123456789abcdef' for c in h),'manifest','Invalid pinned member','manifest.json')
        for project, item in m['projects'].items():
            key(project)
            require(isinstance(item, dict) and {'title', 'active', 'last_closed'} <= set(item),
                    'manifest', 'Invalid project registry entry', 'manifest.json')
        return m

    def project(self, m, project):
        key(project)
        require(project in m['projects'], 'project', 'Project is not registered', project)
        return m['projects'][project]

    def receipt_path(self, request):
        return 'receipts/requests/'+key(request)+'.json'

    def receipt(self, request):
        p = self.receipt_path(request)
        return self.s.json(p, L.MAX_TOTAL*2) if self.s.path(p).exists() else None

    def incomplete(self):
        p = self.s.path('receipts/requests')
        if not p.exists():
            return []
        result = []
        for entry in sorted(p.iterdir()):
            if entry.name == '.gitkeep':
                continue
            require(entry.suffix == '.json', 'receipt', 'Unknown receipt entry', str(entry))
            r = self.s.json('receipts/requests/'+entry.name, L.MAX_TOTAL*2)
            require(r.get('state') in ('pending', 'complete'), 'receipt', 'Invalid receipt state', entry.name)
            if r['state'] == 'pending':
                result.append((entry.stem, r))
        return result

    def snapshot_path(self, digest):
        return 'receipts/engines/'+digest

    def recovery(self, digest, request=None):
        command = [sys.executable, '-I', '-S', '-B',
                   str(self.s.root/self.snapshot_path(digest)/'cli.py'),
                   '--workspace', str(self.s.root)]
        return command + (['recover', '--request', request] if request else [])

    def snapshot_check(self, digest):
        expected = self.s.root/self.snapshot_path(digest)
        require(Path(ENGINE['directory']) == expected,
                'old-kernel-required', 'Use the bound snapshot entry', str(expected), command=self.recovery(digest))
        require(ENGINE['digest'] == digest, 'snapshot', 'Loaded snapshot does not match binding')
        bundle = {n:self.s.read(self.snapshot_path(digest)+'/'+n) for n in L.ENGINE_FILES}
        require(object_hash(bundle) == digest, 'snapshot', 'Snapshot bytes changed', str(expected))

    def engine_gate(self, m, task=None, recovery=False):
        current = self.s.root/L.PACKAGE/'mcp'
        if Path(ENGINE['directory']) != current:
            require(task is not None, 'snapshot-mode', 'Snapshots only settle a bound task or intent')
            self.snapshot_check(task['engine'])
            return
        if recovery:
            raise Refused('snapshot-required', 'Recover using the frozen snapshot', command=self.recovery(task['engine']))
        bundle = {n:self.s.read(L.PACKAGE+'/mcp/'+n) for n in L.ENGINE_FILES}
        pins = {L.PACKAGE+'/mcp/'+n:sha(b) for n,b in bundle.items()}
        require(object_hash(bundle) == ENGINE['digest'] and all(m['adopted'].get(p) == h for p,h in pins.items()),
                'engine-reload-required', 'Loaded kernel, disk kernel and adopted baseline differ; inspect/restart before writing')
        if task:
            require(task['engine'] == ENGINE['digest'], 'old-kernel-required', 'Task is bound to a different kernel',
                    command=self.recovery(task['engine']))

    def ensure_snapshot(self):
        base = self.snapshot_path(ENGINE['digest'])
        if self.s.path(base).exists():
            bundle = {n:self.s.read(base+'/'+n) for n in L.ENGINE_FILES}
            require(object_hash(bundle) == ENGINE['digest'], 'snapshot', 'Existing snapshot has drifted', base)
            return
        stage = 'receipts/staging/engine-'+ENGINE['digest']
        for n, body in ENGINE['bundle'].items():
            p = stage+'/'+n
            actual = self.s.digest(p)
            require(actual in (None, sha(body)), 'snapshot', 'Existing snapshot has drifted', p)
            if actual is None:
                self.s.write(p, body, stage+'/prepare.tmp')
        # A frozen intent must never point at an incomplete recovery program.
        require(self.s.tree(stage) == {n:sha(b) for n,b in ENGINE['bundle'].items()},
                'snapshot', 'Snapshot staging contains unknown content', stage)
        self.s.move(stage,base)

    def replay_steps(self, request, intent):
        temp = 'receipts/staging/'+request+'.tmp'
        path = self.receipt_path(request)
        steps = intent['steps']
        for i in range(intent['cursor'], len(steps)):
            step = steps[i]
            p, kind = step['path'], step['kind']
            if kind == 'write':
                now = self.s.digest(p)
                require(now in (step['before'], step['after']), 'conflict', 'Recovery found a third version', p)
                if now != step['after']:
                    self.s.write(p, unblob(step['body']), temp)
            elif kind == 'delete':
                now = self.s.digest(p)
                require(now in (None, step['before']), 'conflict', 'Delete found a third version', p)
                if now is not None:
                    self.s.remove(p)
            elif kind == 'mkdir':
                self.s.mkdir(p)
            elif kind == 'move':
                dst = step['destination']
                if self.s.path(dst).exists():
                    require(not self.s.path(p).exists() and self.s.tree(dst) == step['tree'],
                            'conflict', 'Archive recovery state differs', dst)
                else:
                    require(self.s.tree(p) == step['tree'], 'conflict', 'Work changed before archival', p)
                    self.s.move(p, dst)
            else:
                raise Refused('receipt', 'Unknown frozen operation')
            intent['cursor'] = i+1
            self.s.write(path, encode(intent), temp)
        complete = {k:intent[k] for k in ('operation','input_sha','engine','python','created_at','result')}
        complete['state'] = 'complete'
        # Atomic final replacement both commits success and drops frozen raw data.
        self.s.write(path, encode(complete), temp)
        return complete['result']

    def commit(self, operation, request, arguments, tx, result):
        tx.preflight()
        intent = dict(state='pending',operation=operation,input_sha=sha(encode(arguments)),
                      engine=ENGINE['digest'],python=ENGINE['python'],cursor=0,steps=tx.steps,
                      created_at=datetime.now(timezone.utc).isoformat(),result=result)
        body = encode(intent)
        require(len(body) <= L.MAX_TOTAL*2, 'size', 'Frozen intent exceeds internal limit')
        self.ensure_snapshot()
        self.s.write(self.receipt_path(request), body, 'receipts/staging/'+request+'.tmp')
        return self.replay_steps(request, intent)

    def recover(self, request):
        with self.s.lock():
            r = self.receipt(request)
            require(r is not None, 'receipt', 'No frozen request', request)
            if r['state'] == 'complete':
                return r['result']
            self.snapshot_check(r['engine'])
            return self.replay_steps(request, r)

    def call(self, operation, arguments):
        require(operation in L.TOOLS, 'operation', 'Unknown Unit tool')
        require(isinstance(arguments, dict), 'arguments', 'Arguments must be an object')
        require(len(encode(arguments)) <= L.MAX_TOTAL, 'size', 'Request exceeds limit')
        if operation == 'check':
            return self.check(**arguments)
        request = key(arguments.get('request_id'))
        with self.s.lock():
            r = self.receipt(request)
            if r:
                require(r['operation'] == operation and r['input_sha'] == sha(encode(arguments)),
                        'request-conflict', 'Request ID was used for different input', request)
                if r['state'] == 'complete':
                    return r['result']
                self.snapshot_check(r['engine'])
                return self.replay_steps(request, r)
            pending = self.incomplete()
            require(not pending, 'pending-transaction', 'Recover the unfinished transaction first',
                    requests=[{'request_id':i,'command':self.recovery(v['engine'],i)} for i,v in pending])
            m = self.manifest()
            task = None
            if operation == 'task_close':
                task = self.project(m, arguments.get('project'))['active']
                require(task is not None, 'task', 'Project has no active task')
            self.engine_gate(m, task)
            tx = Transaction(self.s)
            result = getattr(self, '_'+operation)(m, tx, **arguments)
            return self.commit(operation, request, arguments, tx, result)

    def save_manifest(self, m, tx):
        tx.write('manifest.json', encode(m), self.s.digest('manifest.json'))

    def _project_create(self, m, tx, title, description, request_id):
        text(title); text(description)
        number = 1
        while 'p%06d' % number in m['projects']:
            number += 1
        project = 'p%06d' % number
        root = 'projects/'+project
        require(not self.s.path(root).exists(), 'conflict', 'Unregistered project directory occupies allocated name', root)
        for p in L.PROJECT_DIRS:
            tx.mkdir(root+'/'+p)
        for p in L.PLACEHOLDERS:
            tx.write(root+'/'+p, b'')
        for p, v in L.project_pages(title, description).items():
            tx.write(root+'/'+p, v.encode('utf-8'))
        m['projects'][project] = dict(title=title,active=None,last_closed=None)
        self.save_manifest(m, tx)
        return dict(ok=True,project=project)

    def pending_bytes(self, m, project, kind, source_refs, body, files, ident):
        self.project(m, project)
        require(kind in L.KINDS, 'kind', 'Unknown pending kind')
        sources(source_refs); text(body)
        files = files or {}
        require(isinstance(files, dict) and len(files) <= L.MAX_ITEMS, 'files', 'Invalid attachments')
        for name, payload in files.items():
            rel(name); unblob(payload)
        item = dict(id=ident,kind=kind,source_refs=source_refs,body=body,files=files)
        data = encode(item)
        require(len(data) <= L.MAX_FILE, 'size', 'Pending item exceeds file limit')
        return 'projects/'+project+'/pending/'+kind+'/'+ident+'.json', data

    def _pending_add(self, m, tx, project, kind, source_refs, body, request_id, files=None):
        ident = 'p-'+sha(encode([request_id,'pending']))[:24]
        p, data = self.pending_bytes(m, project, kind, source_refs, body, files, ident)
        tx.write(p, data)
        return dict(ok=True,project=project,id=ident,kind=kind,sha256=sha(data))

    def scopes(self, scopes):
        require(isinstance(scopes, list) and len(scopes) <= L.MAX_ITEMS, 'scope', 'Invalid write scopes')
        for p in scopes:
            rel(p)
            require(p.split('/')[0] in ('understanding','object','tools'),
                    'scope', 'Scope must be in this project understanding/object/tools', p)
        require(len(scopes) == len(set(scopes)), 'scope', 'Duplicate scopes')
        return scopes

    def selected(self, project, selected):
        require(isinstance(selected,list) and 0 < len(selected) <= L.MAX_ITEMS,
                'selection', 'Select one or more pending items')
        result = []
        for v in selected:
            require(isinstance(v, dict) and set(v) == {'id','kind','sha256'}, 'selection', 'Expected id/kind/sha256')
            key(v['id'])
            require(v['kind'] in L.KINDS, 'kind', 'Unknown pending kind')
            p = 'projects/'+project+'/pending/'+v['kind']+'/'+v['id']+'.json'
            require(self.s.digest(p) == v['sha256'], 'stale', 'Pending version changed', p)
            item = self.s.json(p)
            require(item.get('id') == v['id'] and item.get('kind') == v['kind'], 'pending', 'Pending identity differs', p)
            text(item.get('body'),p); sources(item.get('source_refs'),p)
            result.append(dict(v,path=p))
        require(len({v['path'] for v in result}) == len(result), 'selection', 'Duplicate pending item')
        return result

    def scoped_baseline(self, project, scopes):
        root = 'projects/'+project
        result = {}
        for p in scopes:
            path = root+'/'+p
            if self.s.path(path).is_dir():
                result.update({p+'/'+n:h for n,h in self.s.tree(path).items()})
            elif self.s.path(path).exists():
                result[p] = self.s.digest(path)
        return result

    def _task_start(self, m, tx, project, selected, task, write_scopes, request_id):
        entry = self.project(m, project)
        require(entry['active'] is None, 'active-task', 'Only one active task per project', project)
        chosen = self.selected(project, selected)
        scopes = self.scopes(write_scopes)
        text(task)
        ident = 't-'+sha(encode([request_id,'task']))[:24]
        current = 'projects/'+project+'/task/current.md'
        binding = dict(id=ident,selected=chosen,current_sha=sha(task.encode('utf-8')),
                       write_scopes=scopes,baseline=self.scoped_baseline(project,scopes),
                       engine=ENGINE['digest'],python=ENGINE['python'],contract=L.CONTRACT)
        for v in chosen:
            tx.expect(v['path'], v['sha256'])
        # Unowned leftovers are never silently adopted into a new task.
        tree = self.s.tree('projects/'+project+'/task')
        require(set(tree) <= {'work/.gitkeep'} and all(h == sha(b'') for h in tree.values()),
                'task-dirty', 'Task slot contains unowned work', project)
        tx.write(current, task.encode('utf-8'))
        entry['active'] = binding
        self.save_manifest(m,tx)
        return dict(ok=True,project=project,task_id=ident,baseline=sha(encode(binding)),engine=binding['engine'])

    def _task_close(self, m, tx, project, task_id, baseline, outcome, dispositions,
                    checks, transcript_refs, request_id, writes=None, new_pending=None):
        entry = self.project(m,project)
        active = entry['active']
        require(active['id'] == task_id and sha(encode(active)) == baseline,
                'stale', 'Task binding changed', project)
        require(active['contract'] == L.CONTRACT, 'contract', 'Task contract incompatible')
        root = 'projects/'+project
        tx.expect(root+'/task/current.md',active['current_sha'])
        sources(checks)
        require(isinstance(transcript_refs,list) and len(transcript_refs) <= L.MAX_ITEMS,
                'sources', 'Invalid transcript references')
        for r in transcript_refs:
            text(r)
        require(outcome in ('completed','incomplete'), 'outcome', 'Unknown task outcome')
        chosen = {v['id']:v for v in active['selected']}
        require(isinstance(dispositions,dict) and set(dispositions) == set(chosen),
                'dispositions', 'Disposition must cover exactly the selected set')
        for ident, status in dispositions.items():
            require(status in ('done','remaining'), 'disposition', 'Expected done or remaining', ident)
        require(outcome != 'completed' or all(v == 'done' for v in dispositions.values()),
                'incomplete', 'Cannot complete while selected items remain')
        writes = writes or []
        new_pending = new_pending or []
        require(isinstance(writes,list) and len(writes) <= L.MAX_ITEMS and isinstance(new_pending,list)
                and len(new_pending) <= L.MAX_ITEMS, 'size', 'Invalid bounded write list')
        seen, object_after = set(), None
        for w in writes:
            require(isinstance(w,dict) and set(w) == {'path','from_work'}, 'write', 'Write requires path and from_work (null deletes)')
            p = rel(w['path'])
            require(p not in seen and any(p == s or p.startswith(s+'/') for s in active['write_scopes']),
                    'scope', 'Write is duplicate or outside frozen scope', p)
            seen.add(p)
            expected = active['baseline'].get(p)
            body = None
            if w['from_work'] is not None:
                src = root+'/task/work/'+rel(w['from_work'])
                body = self.s.read(src)
                tx.expect(src,sha(body))
                tx.write(root+'/'+p,body,expected)
            else:
                require(expected is not None, 'write', 'Cannot delete an absent baseline', p)
                tx.delete(root+'/'+p,expected)
            if project == 'meta' and p.startswith('object/'):
                if object_after is None:
                    object_after = {L.PACKAGE+'/'+n:h for n,h in self.s.tree(L.PACKAGE).items()}
                    require(object_after == m['adopted'], 'adopted-drift', 'Meta object has unadopted changes')
                if body is None:
                    object_after.pop(root+'/'+p,None)
                else:
                    object_after[root+'/'+p] = sha(body)
                other=[dict(project=n,task_id=e['active']['id'],engine=e['active']['engine'])
                       for n,e in m['projects'].items() if n!=project and e['active'] is not None]
                validate_structure_patch(p,body,other)
        if object_after is not None:
            self.validate_object_paths(object_after)
            m['adopted'] = object_after
        tasktree = self.s.tree(root+'/task')
        closure = dict(task_id=task_id,outcome=outcome,dispositions=dispositions,checks=checks,
                       transcript_refs=transcript_refs,request_id=request_id,engine=active['engine'])
        for ident,v in chosen.items():
            tx.expect(v['path'],v['sha256'])
            if dispositions[ident] == 'done':
                data = self.s.read(v['path'])
                dest = root+'/task/settled/'+ident+'.json'
                tx.write(dest,data)
                tasktree['settled/'+ident+'.json'] = sha(data)
                tx.delete(v['path'],v['sha256'])
        for i, item in enumerate(new_pending):
            require(isinstance(item,dict) and {'project','kind','source_refs','body'} <= set(item)
                    and set(item) <= {'project','kind','source_refs','body','files'}, 'pending', 'Invalid new pending')
            ident = 'p-'+sha(encode([request_id,i]))[:24]
            p,data = self.pending_bytes(m,ident=ident,files=item.get('files'),**{k:item[k] for k in ('project','kind','source_refs','body')})
            tx.write(p,data)
        closurebody = encode(closure)
        tx.write(root+'/task/closure.json',closurebody)
        tasktree['closure.json'] = sha(closurebody)
        archive = 'archive/'+project+'/'+task_id
        tx.move(root+'/task',archive,tasktree)
        tx.mkdir(root+'/task/work')
        # This write happens after moving the old placeholder, so its initial
        # condition refers to the recreated tree, not the pre-transaction tree.
        tx.steps.append(dict(kind='write',path=root+'/task/work/.gitkeep',before=None,after=sha(b''),body=blob(b'')))
        entry['active'] = None
        entry['last_closed'] = dict(task_id=task_id,request_id=request_id,archive=archive,outcome=outcome)
        self.save_manifest(m,tx)
        return dict(ok=True,project=project,task_id=task_id,outcome=outcome,archive=archive)

    def validate_object_paths(self, pins):
        prefix=L.PACKAGE+'/skills/'
        names={p[len(prefix):].split('/')[0] for p in pins if p.startswith(prefix)}
        # File pins omit empty directories. The reserved namespace applies to
        # actual entries too, including before a skill has its first file.
        directory=self.s.path(L.PACKAGE+'/skills')
        for entry in (directory.iterdir() if directory.exists() else []):
            path=self.s.path(prefix+entry.name)
            if path.is_dir():
                names.add(entry.name)
        reserved={'unit-'+v for v in L.VIEWS}
        validate_skill_names(names)
        required={L.PACKAGE+'/rules.md',L.PACKAGE+'/workspace.json'}
        required |= {prefix+n+'/SKILL.md' for n in reserved}
        required |= {L.PACKAGE+'/mcp/'+n for n in L.ENGINE_FILES}
        require(required <= set(pins), 'object', 'Required reconstructable members missing', missing=sorted(required-set(pins)))

    def check(self, scope='workspace', project=None):
        require(scope in ('workspace','project','all') and (scope == 'project') == (project is not None),
                'scope', 'Choose workspace, project with ID, or all')
        issues, baselines, observations = [], {}, []
        def capture(f):
            try:
                return f()
            except Refused as e:
                issues.append(e.report())
            except OSError as e:
                issues.append(dict(ok=False,code='filesystem',detail=str(e),path=str(e.filename or '')))
        m = capture(self.manifest)
        if m is None:
            return dict(ok=False,scope=scope,issues=issues,baselines={})
        if scope in ('workspace','all'):
            def rootcheck():
                allowed=set(L.ROOT_REQUIRED+L.ROOT_OPTIONAL)|set(m['host_entries'])
                for n in L.ROOT_REQUIRED:
                    p=self.s.path(n)
                    require(p.exists(),'missing','Required root entry missing',n)
                    require(p.is_dir() if n in ('projects','receipts') else p.is_file(),'type','Wrong root entry type',n)
                for p in self.s.root.iterdir():
                    require(p.name in allowed,'unmanaged','Unregistered root entry',p.name)
                for n,kind in m['host_entries'].items():
                    require('/' not in rel(n) and n not in L.ROOT_REQUIRED+L.ROOT_OPTIONAL,'host','Invalid host entry',n)
                    p=self.s.path(n)
                    require(kind in ('file','directory') and (p.is_file() if kind == 'file' else p.is_dir()),'host','Host entry missing or wrong type',n)
                self.s.utf8('focus.md')
                actual={p.name for p in self.s.path('projects').iterdir()}
                require(actual == set(m['projects']),'registry','Project registry and directories differ','projects')
            capture(rootcheck)
            pending=capture(self.incomplete)
            if pending:
                issues.append(dict(ok=False,code='pending-transaction',requests=[{'request_id':i,'command':self.recovery(r['engine'],i)} for i,r in pending]))
        ids=list(m['projects']) if scope == 'all' else ([project] if scope == 'project' else [])
        for ident in ids:
            def projectcheck():
                entry=self.project(m,ident)
                root='projects/'+ident
                allowed={'understanding','object','tools','pending','task'}
                require({p.name for p in self.s.path(root).iterdir()} == allowed,'structure','Unexpected project entries',root)
                for p in L.PROJECT_DIRS:
                    require(self.s.path(root+'/'+p).is_dir(),'directory','Missing project directory',root+'/'+p)
                for p in L.PROJECT_FILES:
                    text(self.s.utf8(root+'/'+p),root+'/'+p)
                tree=self.s.tree(root)
                for kind in L.KINDS:
                    for p in self.s.path(root+'/pending/'+kind).iterdir():
                        if p.name == '.gitkeep':
                            continue
                        require(p.suffix == '.json','pending','Unknown pending entry',str(p))
                        item=self.s.json(str(p.relative_to(self.s.root)))
                        require(item.get('id') == p.stem and item.get('kind') == kind,'pending','Pending identity differs',str(p))
                        item_path=str(p.relative_to(self.s.root))
                        text(item.get('body'),item_path);sources(item.get('source_refs'),item_path)
                if entry['active']:
                    a=entry['active']
                    require(self.s.digest(root+'/task/current.md') == a['current_sha'],'task','Frozen task changed',root+'/task/current.md')
                    self.selected(ident,[{k:v[k] for k in ('id','kind','sha256')} for v in a['selected']])
                    if a['python']!=ENGINE['python']:
                        observations.append(dict(code='interpreter-difference',project=ident,
                            recorded=a['python'],current=ENGINE['python'],claim='Reported only; compatibility not established'))
                else:
                    require(set(self.s.tree(root+'/task')) <= {'work/.gitkeep'},'task-dirty','Inactive task contains work',root+'/task')
                if ident == 'meta':
                    pins={L.PACKAGE+'/'+p:h for p,h in self.s.tree(L.PACKAGE).items()}
                    self.validate_object_paths(pins)
                    require(pins == m['adopted'],'adopted-drift','Meta object differs from adopted baseline',L.PACKAGE)
                    require(self.s.json(L.PACKAGE+'/workspace.json') == L.contract(),'contract','Structure projection differs',L.PACKAGE+'/workspace.json')
                    disk={n:self.s.read(L.PACKAGE+'/mcp/'+n) for n in L.ENGINE_FILES}
                    require(object_hash(disk)==ENGINE['digest'],'engine-reload-required',
                            'Read check is using a different kernel than the current disk; restart the entry')
                baselines[ident]=sha(encode(tree))
            capture(projectcheck)
        return dict(ok=not issues,scope=scope,issues=issues,baselines=baselines,observations=observations,
                    projects={k:{'active':v['active']['id'] if v['active'] else None,'last_closed':v['last_closed']} for k,v in m['projects'].items()},
                    engine=dict(loaded=ENGINE['digest'],disk='not-inspected' if 'meta' not in ids else 'checked-against-adopted'))
