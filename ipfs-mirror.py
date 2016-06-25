#!/usr/bin/env python3
from argh import ArghParser, dispatch
import subprocess
import sys
import os


def log(line):
    print(line, file=sys.stderr)


def ipfs(cmd):
    output = subprocess.check_output(['ipfs'] + cmd)
    output = str(output, 'ascii').strip()
    return output


def ipfs_new_dir():
    return ipfs(['object', 'new', 'unixfs-dir'])


def ipfs_add(path):
    return ipfs(['add', '-q', '--', path])


def add(path):
    # TODO: caching
    multihash = ipfs_add(path)
    log('[+] added %r -> %s' % (path, multihash))
    return multihash


def process_folder(root, files):
    def process(root, files):
        for name in files:
            path = os.path.join(root, name)
            multihash = add(path)
            yield name, multihash

    return {name: multihash for name, multihash in process(root, files)}


def ipfs_patch_dir(content):
    folder = ipfs_new_dir()
    for name, multihash in content.items():
        folder = ipfs(['object', 'patch', folder, 'add-link', name, multihash])
    return folder


def resolve(root, tree):
    obj = tree[root]

    for folder in obj['folders']:
        path = os.path.join(root, folder)
        obj['files'][folder] = resolve(path, tree)

    resolved = ipfs_patch_dir(obj['files'])
    log('[+] resolved %r -> %s' % (root, resolved))
    return resolved


def mirror(folder):
    tree = {}
    for root, subs, files in os.walk(folder):
        folder_content = process_folder(root, files)
        obj = {
            'folders': subs,
            'files': folder_content
        }
        tree[root] = obj

    return resolve(folder, tree)


def main():
    parser = ArghParser(description='todo')
    parser.add_commands([mirror, add])
    dispatch(parser)

if __name__ == '__main__':
    main()
