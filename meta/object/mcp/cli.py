"""Standard-library entry; no model, shell, network or SDK is needed."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True


def load_kernel(workspace):
    # Serialize capture with cooperating updates, then invoke only captured code.
    root = Path(workspace).absolute()
    if root.is_symlink():
        raise ValueError('workspace must not be a symlink')
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        directory = Path(__file__).resolve().parent
        spec = importlib.util.spec_from_file_location('_unit_local_loader',directory/'loader.py')
        loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loader)
        return loader.load(directory)
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True)
    commands = parser.add_subparsers(dest='command',required=True)
    c = commands.add_parser('check')
    c.add_argument('--scope',choices=['workspace','project','all'],default='workspace')
    c.add_argument('--project')
    c = commands.add_parser('call')
    c.add_argument('tool')
    c.add_argument('--input',required=True,help='UTF-8 JSON input file, or - for stdin')
    c = commands.add_parser('recover')
    c.add_argument('--request',required=True)
    args = parser.parse_args()
    try:
        package = load_kernel(args.workspace)
        unit = package.mechanics.Unit(args.workspace)
        if args.command == 'check':
            result = unit.call('check',dict(scope=args.scope,project=args.project))
        elif args.command == 'recover':
            result = unit.recover(args.request)
        else:
            if args.input == '-':
                raw = sys.stdin.buffer.read(package.layout.MAX_TOTAL+1)
            else:
                with open(args.input,'rb') as f:
                    raw = f.read(package.layout.MAX_TOTAL+1)
            if len(raw) > package.layout.MAX_TOTAL:
                raise ValueError('input exceeds size limit')
            result = unit.call(args.tool,json.loads(raw.decode('utf-8')))
    except BlockingIOError:
        result = dict(ok=False,code='busy',detail='Workspace mechanical writer is busy',path=args.workspace)
    except Exception as e:
        result = e.report() if hasattr(e,'report') else dict(ok=False,code='input-or-io',detail=str(e))
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0 if result.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
