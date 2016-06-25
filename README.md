# ipfs-mirror

ipfs mirror utils with leveldb cache for immutable files

## Abstract

ipfs-mirror mostly mimics `ipfs add -r`, except that you have cache control with a list of known mutable files. If you add a folder for the first time while using a cache, it's adding the file to ipfs, then store the hash in leveldb. When mirroring the folder again, it's using the hashes found in leveldb, unless it's marked as dynamic file, which are always re-added.

This is useful when mirroring large files into ipfs of which most don't need to be re-hashed.

Add a folder to ipfs recursively:
```
ipfs-mirror mirror --cache ~/.ipfs-mirror debian/ 2>/dev/null
```

Add a folder to ipfs, cache every file by path:
```
ipfs-mirror mirror --cache ~/.ipfs-mirror debian/ 2>/dev/null
```

Add a folder to ipfs, cache every file unless on `~/.ipfs-mirror/cacheignore`
```
ipfs-mirror init ~/.ipfs-mirror
$EDITOR ~/.ipfs-mirror/cacheignore
ipfs-mirror mirror --cache ~/.ipfs-mirror debian/ 2>/dev/null
```

## Cache ignore

Cache ignore bypasses the cache and always re-adds the file, even if there's a hash stored in the cache. This is still work in progress, currently it matches relative paths only:

```
# ignore a folder
dynamic/
# ignore a subfolder
static/wait/no/also/dynamic/
# ignore a specific file
notsure/dynamic.txt
```

Bug: ignoring `notsure/dynamic.txt` also ignores `notsure/dynamic.txt.2`

## Reducing mirrors

It's possible to join multiple mirrors into one meta mirror:

```
# create a new empty folder
FOLDER=`ipfs-mirror empty`
# merge debian/ into our folder
FOLDER=`ipfs-mirror merge "$FOLDER" debian "$DEBIAN_HASH"`
# merge archlinux/ into our folder
FOLDER=`ipfs-mirror merge "$FOLDER" archlinux "$ARCH_HASH"`
# display final mirror hash
echo $FOLDER
```

Trivia: This is syntax candy, the raw ipfs code for this looks like this:

```
FOLDER=`ipfs object new unixfs-dir`
FOLDER=`ipfs object patch "$FOLDER" add-link debian "$DEBIAN_HASH"`
FOLDER=`ipfs object patch "$FOLDER" add-link archlinux "$ARCH_HASH"`
echo $FOLDER
```

## License

GPLv3
