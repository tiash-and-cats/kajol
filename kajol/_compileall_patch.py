import os
import sys
import importlib.util
import py_compile
import struct
import filecmp

from functools import partial
from pathlib import Path

import importlib.util
import sys
import pathlib

@(lambda x: x())
def compileall():
    # Find the stdlib path for compileall
    spec = importlib.util.find_spec("compileall")
    if spec is None or spec.origin is None:
        raise ImportError("Could not locate stdlib compileall")

    # Load a new module object from the file, without using sys.modules
    new_mod = importlib.util.module_from_spec(spec)
    loader = spec.loader
    assert loader is not None
    loader.exec_module(new_mod)
    return new_mod

def compile_file(fullname, ddir=None, force=False, rx=None, quiet=0,
                 legacy=False, optimize=-1,
                 invalidation_mode=None, *, stripdir=None, prependdir=None,
                 limit_sl_dest=None, hardlink_dupes=False):
    """Byte-compile one file.

    Arguments (only fullname is required):

    fullname:  the file to byte-compile
    ddir:      if given, the directory name compiled in to the
               byte-code file.
    force:     if True, force compilation, even if timestamps are up-to-date
    quiet:     full output with False or 0, errors only with 1,
               no output with 2
    legacy:    if True, produce legacy pyc paths instead of PEP 3147 paths
    optimize:  int or list of optimization levels or -1 for level of
               the interpreter. Multiple levels leads to multiple compiled
               files each with one optimization level.
    invalidation_mode: how the up-to-dateness of the pyc will be checked
    stripdir:  part of path to left-strip from source file path
    prependdir: path to prepend to beginning of original file path, applied
               after stripdir
    limit_sl_dest: ignore symlinks if they are pointing outside of
                   the defined path.
    hardlink_dupes: hardlink duplicated pyc files
    """

    if ddir is not None and (stripdir is not None or prependdir is not None):
        raise ValueError(("Destination dir (ddir) cannot be used "
                          "in combination with stripdir or prependdir"))

    success = True
    fullname = os.fspath(fullname)
    stripdir = os.fspath(stripdir) if stripdir is not None else None
    name = os.path.basename(fullname)

    dfile = None

    if ddir is not None:
        dfile = os.path.join(ddir, name)

    if stripdir is not None:
        fullname_parts = fullname.split(os.path.sep)
        stripdir_parts = stripdir.split(os.path.sep)

        if stripdir_parts != fullname_parts[:len(stripdir_parts)]:
            if quiet < 2:
                print("The stripdir path {!r} is not a valid prefix for "
                      "source path {!r}; ignoring".format(stripdir, fullname))
        else:
            dfile = os.path.join(*fullname_parts[len(stripdir_parts):])

    if prependdir is not None:
        if dfile is None:
            dfile = os.path.join(prependdir, fullname)
        else:
            dfile = os.path.join(prependdir, dfile)

    if isinstance(optimize, int):
        optimize = [optimize]

    # Use set() to remove duplicates.
    # Use sorted() to create pyc files in a deterministic order.
    optimize = sorted(set(optimize))

    if hardlink_dupes and len(optimize) < 2:
        raise ValueError("Hardlinking of duplicated bytecode makes sense "
                          "only for more than one optimization level")

    if rx is not None:
        mo = rx.search(fullname)
        if mo:
            return success

    if limit_sl_dest is not None and os.path.islink(fullname):
        if Path(limit_sl_dest).resolve() not in Path(fullname).resolve().parents:
            return success

    opt_cfiles = {}

    if os.path.isfile(fullname):
        for opt_level in optimize:
            if legacy:
                opt_cfiles[opt_level] = fullname + 'c'
            else:
                if opt_level >= 0:
                    opt = opt_level if opt_level >= 1 else ''
                    cfile = (importlib.util.cache_from_source(
                             fullname, optimization=opt))
                    opt_cfiles[opt_level] = cfile
                else:
                    cfile = importlib.util.cache_from_source(fullname)
                    opt_cfiles[opt_level] = cfile

        head, tail = name[:-3], name[-3:]
        if tail == '.py':
            if not force:
                try:
                    mtime = int(os.stat(fullname).st_mtime)
                    expect = struct.pack('<4sLL', importlib.util.MAGIC_NUMBER,
                                         0, mtime & 0xFFFF_FFFF)
                    for cfile in opt_cfiles.values():
                        with open(cfile, 'rb') as chandle:
                            actual = chandle.read(12)
                        if expect != actual:
                            break
                    else:
                        return success
                except OSError:
                    pass
            if not quiet:
                print('Compiling {!r}...'.format(fullname))
            try:
                for index, opt_level in enumerate(optimize):
                    cfile = opt_cfiles[opt_level]
                    ok = py_compile.compile(fullname, cfile,
                                            f"<compiled {dfile or fullname}>", 
                                            True, optimize=opt_level,
                                            invalidation_mode=\
                                            invalidation_mode)
                    if index > 0 and hardlink_dupes:
                        previous_cfile = opt_cfiles[optimize[index - 1]]
                        if filecmp.cmp(cfile, previous_cfile, shallow=False):
                            os.unlink(cfile)
                            os.link(previous_cfile, cfile)
            except py_compile.PyCompileError as err:
                success = False
                if quiet >= 2:
                    return success
                elif quiet:
                    print('*** Error compiling {!r}...'.format(fullname))
                else:
                    print('*** ', end='')
                # escape non-printable characters in msg
                encoding = sys.stdout.encoding or sys.getdefaultencoding()
                msg = err.msg.encode(encoding, errors='backslashreplace').decode(encoding)
                print(msg)
            except (SyntaxError, UnicodeError, OSError) as e:
                success = False
                if quiet >= 2:
                    return success
                elif quiet:
                    print('*** Error compiling {!r}...'.format(fullname))
                else:
                    print('*** ', end='')
                print(e.__class__.__name__ + ':', e)
            else:
                if ok == 0:
                    success = False
    return success

compileall.compile_file = compile_file