"""Load operative modules from exactly the bytes whose identity is recorded."""
import hashlib
import json
from pathlib import Path
import sys
import types

FILES = ('cli.py', 'loader.py', 'layout.py', 'storage.py', 'mechanics.py', 'server.py')


def identity(bundle):
    pins = {k: hashlib.sha256(v).hexdigest() for k, v in sorted(bundle.items())}
    return hashlib.sha256((json.dumps(pins, sort_keys=True, separators=(',', ':'))+'\n').encode()).hexdigest()


def load(directory):
    directory = Path(directory).resolve(strict=True)
    bundle = {}
    for name in FILES:
        p = directory / name
        if p.is_symlink() or not p.is_file() or p.stat().st_size > 8*1024*1024:
            raise ValueError('invalid engine member: '+name)
        bundle[name] = p.read_bytes()
    digest = identity(bundle)
    # Every instance has its own modules; no cwd/PYTHONPATH/global mechanics import.
    prefix = '_k4_'+digest+'_'+str(id(bundle))
    package = types.ModuleType(prefix)
    package.__path__ = []
    sys.modules[prefix] = package
    for name in ('layout', 'storage', 'mechanics'):
        fullname = prefix+'.'+name
        module = types.ModuleType(fullname)
        module.__package__ = prefix
        module.__file__ = str(directory/(name+'.py'))
        sys.modules[fullname] = module
        exec(compile(bundle[name+'.py'], module.__file__, 'exec'), module.__dict__)
        setattr(package, name, module)
    package.mechanics.ENGINE = {'digest':digest, 'bundle':bundle, 'directory':str(directory),
                                'python':sys.version, 'contract':package.layout.contract()}
    if tuple(package.layout.ENGINE_FILES) != FILES:
        raise ValueError('loader closure and declared engine files differ')
    return package
