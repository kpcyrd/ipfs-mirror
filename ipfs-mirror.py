#!/usr/bin/env python3
from argh import ArghParser, arg, dispatch, wrap_errors
import plyvel
import subprocess
import json
import sys
import os


class Cache(object):
    def __init__(self, path=None, progress=None):
        self.path = path
        self.db = self.open('cache.db')
        self.stat_db = self.open('stat.db')
        self._goipfs_2938_db = self.open('_goipfs_2938.db')
        self.progress = progress
        self.filter = list(self.load_filter())

    def ensure_exists(self):
        os.makedirs(self.path, exist_ok=True)

    def open(self, name='cache.db'):
        if self.path:
            self.ensure_exists()
            path = os.path.join(self.path, name)
            return LevelDBStore(path)
        else:
            return NullStore(self.path)

    def load_filter(self):
        if self.path:
            self.ensure_exists()
            path = os.path.join(self.path, 'cacheignore')
            try:
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        yield line
            except FileNotFoundError:
                pass

    def add(self, path, **kwargs):
        multihash = self.try_cache(path, lambda path: ipfs_add(path), **kwargs)
        return multihash

    def try_cache(self, path, func, root=None):
        self.progress.log_n('[+] %-100r ... ' % path)

        if self.skips_cache(root, path):
            self.progress.log_n('NOCACHE ... ')
            self.progress.log_size(path)
            multihash = func(path)
        else:
            multihash = self.db.get(path)
            if multihash:
                self.progress.log_n('HIT ... ')
            else:
                self.progress.log_n('MISS ... ')
                self.progress.log_size(path)
                multihash = func(path)
                self.db.put(path, multihash)

        self.progress.increase()
        self.progress.log('%s' % multihash)
        return multihash

    def skips_cache(self, root, path):
        if root:
            relative = path[len(root):]
            if any(relative.startswith(x) for x in self.filter):
                return True
            return os.path.basename(path) in self.filter

    def close(self):
        self.db.close()

    def get(self, key):
        return self.db.get(key)

    def put(self, key, value):
        return self.db.put(key, value)


class FolderWalker(object):
    def __init__(self, root, cache=None, progress=None):
        self.root = root
        if not cache:
            cache = Cache(cache)
        self.cache = cache
        self.progress = progress

    def add(self, path):
        return self.cache.add(path, root=self.root)

    def traverse(self):
        tree = {}
        self.progress.total = sum(
                                  len(files)
                                  for _, _, files in
                                  os.walk(self.root))
        for root, subs, files in os.walk(self.root):
            subs.sort()
            files.sort()

            folder_content = self._process_folder(root, files)
            obj = {
                'folders': subs,
                'files': folder_content
            }
            tree[root] = obj
        return tree

    def _process_folder(self, root, files):
        def process(root, files):
            for name in files:
                path = os.path.join(root, name)
                multihash = self.add(path)
                yield name, multihash

        return {name: multihash for name, multihash in process(root, files)}


class NullStore(object):
    def __init__(self, path):
        pass

    def close(self):
        pass

    def get(self, key):
        pass

    def put(self, key, value):
        pass


class LevelDBStore(NullStore):
    def __init__(self, path):
        self.db = plyvel.DB(path, create_if_missing=True)

    def close(self):
        return self.db.close()

    def get(self, key):
        key = bytes(key, 'utf8')
        value = self.db.get(key)
        if value:
            value = str(value, 'utf8')
        return value

    def put(self, key, value):
        key = bytes(key, 'utf8')
        value = bytes(value, 'utf8')
        return self.db.put(key, value)


class Progress(object):
    text_only = False

    def __init__(self, total=-1):
        self.progress = 0
        self.total = total
        self.silent = False
        self.dirty = False
        self.buffer = ''

    def log(self, line):
        self.reset()
        log(self.buffer + line)
        self.buffer = ''
        self.update()

    def log_n(self, chunk):
        self.reset()
        self.buffer += chunk
        if not Progress.text_only:
            log_n(self.buffer)
        self.update()

    def log_size(self, path):
        self.reset()
        size = os.path.getsize(path)
        size = human_size(size)
        self.log_n('%s ... ' % size)
        self.update()

    def update(self):
        if self.silent or Progress.text_only:
            return

        if not self.dirty:
            log('')
            self.dirty = True

        if self.total < 0:
            log_n('\r[%%] %d / ??' % (self.progress))
        else:
            log_n('\r[%%] %d / %d' % (self.progress, self.total))

    def finish(self):
        if Progress.text_only:
            return
        self.reset()
        self.dirty = True
        self.update()
        log('')
        self.reset_line()
        self.silent = True

    def reset(self):
        if self.silent or Progress.text_only:
            return

        if self.dirty:
            log_n('\033[1A\r')
            self.dirty = False

        self.reset_line()
        log_n('\033[2K\r')

    def reset_line(self):
        if not Progress.text_only:
            log_n('\033[2K\r')

    def increase(self, num=1):
        self.progress += num


def log(line):
    print(line, file=sys.stderr)


def log_n(chunk):
    print(chunk, end='', flush=True, file=sys.stderr)


def human_size(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return '%5.1f %3s%s' % (num, unit, suffix)
        num /= 1024.0
    return '%.1f %s%s' % (num, 'Yi', suffix)


def ipfs(cmd):
    output = subprocess.check_output(['ipfs'] + cmd)
    output = str(output, 'ascii').strip()
    return output


@wrap_errors([KeyboardInterrupt])
def empty():
    'Create empty folder'
    return ipfs(['object', 'new', 'unixfs-dir'])


def ipfs_add(path):
    return ipfs(['add', '-q', '--progress=false', '--', path])


@arg('--cache', metavar='path', help='cache location')
@wrap_errors([KeyboardInterrupt])
def add(path, cache=None):
    'Get ipfs path for file'

    cache = Cache(cache)
    multihash = cache.add(path)
    cache.close()

    return multihash


@wrap_errors([KeyboardInterrupt])
def merge(root, name, multihash):
    'Merge folder into another folder'
    return ipfs(['object', 'patch', root, 'add-link', name, multihash])


def ipfs_patch_dir(content, progress=None, _goipfs_2938_db=None):
    folder = empty()
    for name, multihash in sorted(content.items()):
        _key = '%r/%r/%r' % (folder, multihash, name)
        _value = None

        if _goipfs_2938_db:
            _value = _goipfs_2938_db.get(_key)

        if _value:
            folder = _value
        else:
            folder = merge(folder, name, multihash)
            if _goipfs_2938_db:
                _goipfs_2938_db.put(_key, folder)

        if progress:
            progress.increase()
            progress.update()
    return folder


def stat(multihash, db=None):
    def parse(output):
        for line in output.split('\n'):
            yield line.split(': ')

    if db:
        cached = db.get(multihash)
        if cached:
            return json.loads(cached)

    output = ipfs(['object', 'stat', '--', multihash])
    obj = {key: value for key, value in parse(output)}

    if db:
        db.put(multihash, json.dumps(obj))

    return obj


def put(obj):
    p = subprocess.Popen(['ipfs', 'object', 'put'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    data = json.dumps(obj).encode('utf-8')
    stdout, _ = p.communicate(data)
    output = str(stdout, 'utf-8').strip()
    return output.split(' ')[1] # TODO: find a cleaner way


def files2obj(files, stat_db=None, progress=None):
    ipfs_obj = {'Links':[],'Data':'\u0008\u0001'}

    for name, multihash in files.items():
        x = stat(multihash, db=stat_db)
        y = {
            'Name': name,
            'Hash': multihash,
            'Size': int(x['CumulativeSize'])
        }
        ipfs_obj['Links'].append(y)
        if progress:
            progress.increase()
            progress.update()

    return ipfs_obj


def resolve(root, tree, stat_db=None, _goipfs_2938_db=None):
    obj = tree[root]

    for folder in obj['folders']:
        path = os.path.join(root, folder)
        obj['files'][folder] = resolve(path, tree, stat_db=stat_db, _goipfs_2938_db=_goipfs_2938_db)


    total = len(obj['files'].items())
    progress = Progress(total)
    progress.log_n('[*] resolving %r ... ' % root)

    ipfs_obj = files2obj(obj['files'], stat_db=stat_db, progress=progress)
    resolved = put(ipfs_obj)
    #resolved = ipfs_patch_dir(obj['files'], _goipfs_2938_db=_goipfs_2938_db, progress=progress) # TODO

    progress.log(resolved)
    progress.finish()

    return resolved


@arg('--cache', metavar='path', help='cache location')
@wrap_errors([KeyboardInterrupt])
def mirror(folder, cache=None, text_only=False):
    'Mirror a folder'

    Progress.text_only = text_only

    progress = Progress()
    cache = Cache(cache, progress=progress)
    walker = FolderWalker(folder, cache, progress=progress)
    tree = walker.traverse()
    progress.finish()
    cache.close()

    return resolve(folder, tree, stat_db=cache.stat_db, _goipfs_2938_db=cache._goipfs_2938_db)


@wrap_errors([KeyboardInterrupt])
def init(path):
    'Initialize cache'
    cache = Cache(path)
    ignore = os.path.join(path, 'cacheignore')
    with open(ignore, 'w'):
        pass


def main():
    parser = ArghParser(description='todo')
    parser.add_commands([mirror, add, empty, merge, init])
    dispatch(parser)

if __name__ == '__main__':
    main()
