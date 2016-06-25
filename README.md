# ipfs-mirror

ipfs mirror utils with leveldb cache for immutable files

## Abstract

ipfs-mirror mostly mimics `ipfs add -r`, except that you can control if it's going to recalculate a hash or use a cached hash. This is useful if you have a large volume of files and you already know which files don't change their content and therefore don't need to be recalculate a hash.

Add a folder to ipfs recursively:
```
ipfs-mirror mirror --cache ~/.ipfs-mirror debian/ 2>/dev/null
```

Add a folder to ipfs, cache every file by name:
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
