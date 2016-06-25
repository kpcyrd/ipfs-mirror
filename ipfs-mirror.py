#!/usr/bin/env python3
from argh import ArghParser, arg, dispatch
import plyvel
import subprocess
import sys
import os


class Cache(object):
    def __init__(self, path):
        self.path = path
        self.db = self.open()

    def ensure_exists(self, path):
        os.makedirs(self.path, exist_ok=True)

    def open(self):
        if self.path:
            self.ensure_exists()
            path = os.path.join(self.path, 'cache.db')
            return LevelDBStore(path)
        else:
            return NullStore(self.path)

    def close(self):
        self.db.close()

    def get(self, key):
        return self.db.get(key)

    def put(self, key, value):
        return self.db.put(key, value)


class NullStore(object):
    def __init__(self, path):
        self._implicit_close = False
        pass

    def implicit_close(self):
        if self._implicit_close:
            self.close()

    def close(self):
        pass

    def get(self, key):
        pass

    def put(self, key, value):
        pass


class LevelDBStore(NullStore):
    def __init__(self, path, implicit_close=False):
        self.db = plyvel.DB(path, create_if_missing=True)
        self._implicit_close = implicit_close

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


def ipfs(cmd):
    output = subprocess.check_output(['ipfs'] + cmd)
    output = str(output, 'ascii').strip()
    return output


def empty():
    'Create empty folder'
    return ipfs(['object', 'new', 'unixfs-dir'])


def ipfs_add(path):
    multihash = ipfs(['add', '-q', '--', path])
    log('[+] added %r -> %s' % (path, multihash))
    return multihash


def try_cache(db, path):
    multihash = db.get(path)

    if multihash:
        log('[+] found %r -> %s' % (path, multihash))
    else:
        multihash = ipfs_add(path)
        db.put(path, multihash)

    return multihash


def store_factory(db):
    if db:
        if type(db) is str:
            db = LevelDBStore(db, implicit_close=True)
    else:
        db = NullStore(None)

    return db


@arg('--db')
def add(path, db=None):
    'Get ipfs path for file'

    db = store_factory(db)
    multihash = try_cache(db, path)
    db.implicit_close()

    return multihash


def merge(root, name, multihash):
    'Merge folder into another folder'
    return ipfs(['object', 'patch', root, 'add-link', name, multihash])


def process_folder(root, files, cache=None):
    if cache:
        cache = cache.db

    def process(root, files):
        for name in files:
            path = os.path.join(root, name)
            multihash = add(path, db=cache)
            yield name, multihash

    return {name: multihash for name, multihash in process(root, files)}


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

    tree = {}
    for root, subs, files in os.walk(folder):
        folder_content = process_folder(root, files, cache=cache)
        obj = {
            'folders': subs,
            'files': folder_content
        }
        tree[root] = obj

    cache.close()

    return resolve(folder, tree)


def main():
    parser = ArghParser(description='todo')
    parser.add_commands([mirror, add, empty, merge])
    dispatch(parser)

if __name__ == '__main__':
    main()
