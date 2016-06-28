#!/usr/bin/env python3
from argh import ArghParser, arg, dispatch
import plyvel
import subprocess
import sys
import os


class Cache(object):
    def __init__(self, path=None):
        self.path = path
        self.db = self.open()
        self.filter = list(self.load_filter())

    def ensure_exists(self):
        os.makedirs(self.path, exist_ok=True)

    def open(self):
        if self.path:
            self.ensure_exists()
            path = os.path.join(self.path, 'cache.db')
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
        log_n('[+] %r ... ' % path)

        if self.skips_cache(root, path):
            log_n('NOCACHE ... ')
            multihash = func(path)
        else:
            multihash = self.db.get(path)
            if multihash:
                log_n('HIT ...')
            else:
                log_n('MISS ... ')
                multihash = func(path)
                self.db.put(path, multihash)

        log('%r' % multihash)
        return multihash

    def skips_cache(self, root, path):
        if root:
            relative = path[len(root):]
            return any(relative.startswith(x) for x in self.filter)

    def close(self):
        self.db.close()

    def get(self, key):
        return self.db.get(key)

    def put(self, key, value):
        return self.db.put(key, value)


class FolderWalker(object):
    def __init__(self, root, cache=None):
        self.root = root
        if not cache:
            cache = Cache(cache)
        self.cache = cache

    def add(self, path):
        return self.cache.add(path, root=self.root)

    def traverse(self):
        tree = {}
        for root, subs, files in os.walk(self.root):
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


def log(line):
    print(line, file=sys.stderr)


def log_n(chunk):
    print(chunk, end='', flush=True, file=sys.stderr)


def ipfs(cmd):
    output = subprocess.check_output(['ipfs'] + cmd)
    output = str(output, 'ascii').strip()
    return output


def empty():
    'Create empty folder'
    return ipfs(['object', 'new', 'unixfs-dir'])


def ipfs_add(path):
    return ipfs(['add', '-q', '--progress=false', '--', path])


@arg('--cache', metavar='path', help='cache location')
def add(path, cache=None):
    'Get ipfs path for file'

    cache = Cache(cache)
    multihash = cache.add(path)
    cache.close()

    return multihash


def merge(root, name, multihash):
    'Merge folder into another folder'
    return ipfs(['object', 'patch', root, 'add-link', name, multihash])


def ipfs_patch_dir(content):
    folder = empty()
    for name, multihash in content.items():
        folder = merge(folder, name, multihash)
    return folder


def resolve(root, tree):
    obj = tree[root]

    for folder in obj['folders']:
        path = os.path.join(root, folder)
        obj['files'][folder] = resolve(path, tree)

    resolved = ipfs_patch_dir(obj['files'])
    log('[+] resolved %r -> %s' % (root, resolved))
    return resolved


@arg('--cache', metavar='path', help='cache location')
def mirror(folder, cache=None):
    'Mirror a folder'

    cache = Cache(cache)
    walker = FolderWalker(folder, cache)
    tree = walker.traverse()
    cache.close()

    return resolve(folder, tree)


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
