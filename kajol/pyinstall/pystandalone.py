import re
import sys
import tarfile
import requests
import os
import ctypes
import platform
import shellingham
import subprocess
import shutil
import re
from contextlib import contextmanager
from llvmlite import binding as llvm
from pathlib import Path
from packaging.version import Version

import kajol
from kajol.install import HTML, add_executable_bit
from kajol.pyinstall.shared import (PYVERSIONS, download, latest_python,
                             _installed_python, list_installed_python,
                             uninstall_python, shell, list_available_python,
                             _get_latest_installed, exec_python,
                             add_to_windows_user_path)

llvm.initialize_native_target()
llvm.initialize_native_asmprinter()

@contextmanager
def _make_script(name):
    if sys.platform == "win32":
        with open(name + ".bat", "w") as f:
            f.write("@echo off\n")
            yield f
    else:
        with open(name, "w") as f:
            f.write("#!/bin/sh\n")
            yield f
        try:
            add_executable_bit(name)
        except: pass

_EXEC_SUFFIX = ".exe" if sys.platform == "win32" else ""
_ALLARGS = "%*" if os.name == "nt" else "$*"

def _pystand_get_latest_release():
    url = "https://raw.githubusercontent.com/astral-sh/" + \
          "python-build-standalone/latest-release/latest-release.json"
    headers = {'User-Agent': f"kajol/{kajol.__version__}"}
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def taropen(path):
    def _tar_zst_open(path):
        if sys.version_info >= (3, 14):
            return tarfile.open(path, "r:zst")
        else:
            import zstandard as zstd

            @contextmanager
            def _TarZstFile(path):
                with open(path, "rb") as fh:
                    dctx = zstd.ZstdDecompressor()
                    with dctx.stream_reader(fh) as reader:
                        yield tarfile.open(fileobj=reader, mode="r|")

            return _TarZstFile(path)

    if path.endswith(".tar.zst"):
        return _tar_zst_open(path)
    else:
        return tarfile.open(path)

def get_best_installer(version, auto_retry):
    def _inner(version):
        latest_release = _pystand_get_latest_release()
        url_prefix = "https://github.com/astral-sh/" + \
                     "python-build-standalone/releases/download/" + \
                     latest_release["tag"] + "/"

        best_tar = f"cpython-{version}+{latest_release["tag"]
                   }-{llvm.get_process_triple()}-install_only.tar"

        best_tar_zst_url = url_prefix + best_tar + ".zst"
        best_tar_gz_url = url_prefix + best_tar + ".gz"

        res = requests.head(best_tar_zst_url)
        if res.status_code == 404:
            res = requests.head(best_tar_gz_url)
            if res.status_code == 404:
                return None
            elif 200 <= res.status_code < 400:
                return best_tar_gz_url
            else:
                res.raise_for_status()
        elif 200 <= res.status_code < 400:
            return best_tar_zst_url
        else:
            res.raise_for_status()

    res = _inner(version)

    if not res:
        if auto_retry:
            v = Version(version)
            if v.micro == 0:
                return str(v), None

            prev_v = Version(f"{v.major}.{v.minor}.{v.micro-1}")
            print(f"couldn't find an installer for {v}, trying {prev_v}")
            return get_best_installer(str(prev_v), True)
        else:
            return version, None
    else:
        return version, res
#
def install_python(version, auto_retry):
    version, url = get_best_installer(version, auto_retry)
    if not url:
        raise FileNotFoundError("We don't have that kind of cheese.")

    target_dir = Path.home() / ".kajol" / "python" / version
    target_dir.mkdir(parents=True, exist_ok=True)

    if url.endswith(".tar.zst"):
        zip_path = target_dir / f"python-{version}.tzst"
    else:
        zip_path = target_dir / f"python-{version}.tgz"

    download(url, zip_path)

    print("extracting...")
    with taropen(str(zip_path)) as tar:
        members_to_extract = []

        target_prefix = "python/"

        for member in tar.getmembers():
            if member.name.startswith("python/"):
                if member.name == target_prefix:
                    continue

                relative_path = os.path.relpath(member.name, target_prefix)
                member.name = relative_path

                members_to_extract.append(member)

        tar.extractall(
            path=target_dir, members=members_to_extract, filter='data'
        )

    # make "binaries"
    bin_dir = Path(target_dir / ("Scripts" if os.name == "nt" else "bin"))
    bin_dir.mkdir(exist_ok=True)

    v = Version(version)
    for x in ("python", f"python{v.major}", f"python{v.major}.{v.minor}"):
        script = (
            f"{target_dir.resolve() / ('python' + _EXEC_SUFFIX)} {_ALLARGS}"
        )
        with _make_script(str(bin_dir / x)) as f:
            f.write(script)

    for x in ("pythonw", f"pythonw{v.major}", f"pythonw{v.major}.{v.minor}"):
        script = (
            f"{target_dir.resolve() / ('pythonw' + _EXEC_SUFFIX)} {_ALLARGS}"
        )
        with _make_script(str(bin_dir / x)) as f:
            f.write(script)

    print(f"Python {version} installed to {target_dir}")

    if sys.platform == "win32":
        if input("add Python install to PATH? ").lower().startswith("y"):
            add_to_windows_user_path(str(bin_dir))
    else:
        print("to add the Python install to PATH, you will need to",
              "modify your .bashrc/.zshrc/etc.")
#