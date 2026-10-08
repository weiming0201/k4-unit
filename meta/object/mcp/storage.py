"""Bounded local I/O. No shell, network, model or semantic decisions."""
import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

from .layout import MAX_FILE, MAX_TEXT, MAX_FILES, MAX_TOTAL


class Refused(ValueError):
    def __init__(self, code, detail, path='', **extra):
        self.code, self.detail, self.path, self.extra = code, detail, path, extra
        super().__init__(detail)

    def report(self):
        return {'ok': False, 'code': self.code, 'detail': self.detail, 'path': self.path, **self.extra}


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def sha(body):
    return hashlib.sha256(body).hexdigest()


def blob(body):
    return base64.b64encode(body).decode('ascii')


def unblob(value):
    try:
        body = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        raise Refused('payload', 'Expected canonical base64 bytes') from None
    if len(body) > MAX_FILE:
        raise Refused('size', 'File payload exceeds limit')
    return body


def key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', value):
        raise Refused('identifier', 'Expected 1-64 lowercase ASCII letters/digits/_/-')
    return value


def rel(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise Refused('path', 'Expected a canonical relative POSIX path', str(value))
    p = PurePosixPath(value)
    if p.is_absolute() or str(p) != value or any(x in ('.', '..', '') for x in value.split('/')):
        raise Refused('path', 'Non-canonical or escaping path', value)
    return value


def text(value, path=''):
    if not isinstance(value, str) or not value.strip():
        raise Refused('text', 'Expected nonempty text', path)
    try:
        length = len(value.encode('utf-8'))
    except UnicodeError:
        raise Refused('utf8', 'Invalid UTF-8 text', path) from None
    if length > MAX_TEXT:
        raise Refused('size', 'Semantic text exceeds limit', path)
    return value


class Store:
    def __init__(self, root, observer=None):
        raw = Path(root).absolute()
        self.root = raw.parent.resolve(strict=True) / raw.name
        if not stat.S_ISDIR(self.root.lstat().st_mode):
            raise Refused('root', 'Workspace must be a real directory', str(root))
        self.observer = observer

    def event(self, phase, operation, path):
        if self.observer:
            self.observer(phase, operation, path)

    def path(self, name):
        rel(name)
        p = self.root
        for index, part in enumerate(name.split('/')):
            p = p / part
            try:
                mode = p.lstat().st_mode
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(mode):
                raise Refused('symlink', 'Managed paths must not traverse symlinks', name)
            if index < len(name.split('/')) - 1 and not stat.S_ISDIR(mode):
                raise Refused('path', 'Path parent is not a directory', name)
        return p

    def read(self, name, maximum=MAX_FILE):
        p = self.path(name)
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            s = os.fstat(fd)
            if not stat.S_ISREG(s.st_mode) or s.st_size > maximum:
                raise Refused('file', 'Expected bounded regular file', name)
            with os.fdopen(fd, 'rb', closefd=False) as f:
                body = f.read(maximum + 1)
            if len(body) > maximum:
                raise Refused('size', 'File grew beyond limit', name)
            return body
        finally:
            os.close(fd)

    def json(self, name, maximum=MAX_FILE):
        body = self.read(name, maximum)
        try:
            return json.loads(body.decode('utf-8'))
        except UnicodeError:
            raise Refused('utf8', 'Invalid UTF-8 metadata', name) from None
        except ValueError:
            raise Refused('json', 'Invalid JSON metadata', name) from None

    def utf8(self, name):
        try:
            return self.read(name, MAX_TEXT).decode('utf-8')
        except UnicodeError:
            raise Refused('utf8', 'Invalid UTF-8 text', name) from None

    def digest(self, name):
        try:
            return sha(self.read(name))
        except FileNotFoundError:
            return None

    def mkdir(self, name):
        p = self.path(name)
        if p.exists():
            if not p.is_dir():
                raise Refused('directory', 'Expected directory', name)
            return
        if p.parent != self.root:
            self.mkdir(str(p.parent.relative_to(self.root)))
        self.event('before', 'mkdir', name)
        p.mkdir(mode=0o700)
        self.sync(p.parent)
        self.event('after', 'mkdir', name)

    @staticmethod
    def sync(path):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def write(self, name, body, temporary):
        if len(body) > MAX_TOTAL * 2:
            raise Refused('size', 'Internal transaction exceeds limit', name)
        p, tmp = self.path(name), self.path(temporary)
        if p == tmp:
            raise Refused('path', 'Temporary path equals destination', name)
        for parent in (p.parent, tmp.parent):
            if parent != self.root:
                self.mkdir(str(parent.relative_to(self.root)))
        self.event('before', 'stage', temporary)
        if tmp.exists() and not stat.S_ISREG(tmp.lstat().st_mode):
            raise Refused('file', 'Temporary path is not a regular file', temporary)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise Refused('file', 'Temporary file descriptor is not regular', temporary)
            with os.fdopen(fd, 'wb', closefd=False) as f:
                f.write(body); f.flush(); os.fsync(fd)
        finally:
            os.close(fd)
        self.event('after', 'stage', temporary)
        self.event('before', 'replace', name)
        os.replace(tmp, p)
        self.sync(p.parent)
        self.event('after', 'replace', name)

    def remove(self, name):
        p = self.path(name)
        self.event('before', 'unlink', name)
        p.unlink()
        self.sync(p.parent)
        self.event('after', 'unlink', name)

    def tree(self, name):
        root = self.path(name)
        result, total = {}, 0
        if not root.is_dir():
            raise Refused('directory', 'Expected tree directory', name)
        for parent, dirs, files in os.walk(root, followlinks=False):
            for n in dirs + files:
                self.path(str((Path(parent)/n).relative_to(self.root)))
            for n in sorted(files):
                p = Path(parent)/n
                r = str(p.relative_to(self.root))
                body = self.read(r)
                total += len(body)
                result[str(p.relative_to(root))] = sha(body)
                if len(result) > MAX_FILES or total > MAX_TOTAL:
                    raise Refused('size', 'Tree exceeds declared bound', name)
        return result

    def move(self, src, dst):
        a, b = self.path(src), self.path(dst)
        if b.exists():
            raise Refused('conflict', 'Archive destination exists', dst)
        self.mkdir(str(b.parent.relative_to(self.root)))
        if a.stat().st_dev != b.parent.stat().st_dev:
            raise Refused('filesystem', 'Archive must stay on one filesystem', dst)
        self.event('before', 'rename', src)
        os.rename(a, b)
        self.sync(a.parent); self.sync(b.parent)
        self.event('after', 'rename', src)

    @contextmanager
    def lock(self):
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Refused('busy', 'Workspace mechanical writer is busy') from None
            yield
        finally:
            os.close(fd)
