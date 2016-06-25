#!/usr/bin/env python3
from argh import ArghParser, arg, dispatch
import plyvel
import subprocess
import sys
import os


class Cache(object):
    def __init__(self, path):
        os.makedirs(path, exist_ok=True)
        self.path = path
        self.db = self.open()

    def open(self):
        path = os.path.join(self.path, 'cache.db')
        return plyvel.DB(path, create_if_missing=True)

    def close(self):
        self.db.close()

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
    key = bytes(path, 'utf8')
    multihash = db.get(key)

    if multihash:
        multihash = str(multihash, 'utf8')
        log('[+] found %r -> %s' % (path, multihash))
    else:
        multihash = ipfs_add(path)
        db.put(key, bytes(multihash, 'utf8'))

    return multihash


@arg('--db')
def add(path, db=None):
    'Get ipfs path for file'

    if db:
        keep_open = True
        if type(db) is str:
            db = plyvel.DB(db, create_if_missing=True)
            keep_open = False

        multihash = try_cache(db, path)

        if not keep_open:
            db.close()
    else:
        multihash = ipfs_add(path)

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

    if cache:
        cache = Cache(cache)

    tree = {}
    for root, subs, files in os.walk(folder):
        folder_content = process_folder(root, files, cache=cache)
        obj = {
            'folders': subs,
            'files': folder_content
        }
        tree[root] = obj

    if cache:
        cache.close()

    return resolve(folder, tree)


def main():
    parser = ArghParser(description='todo')
    parser.add_commands([mirror, add, empty, merge])
    dispatch(parser)

if __name__ == '__main__':
    main()
