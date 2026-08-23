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

llvm.initialize_native_target()
llvm.initialize_native_asmprinter()

try:
    import winreg
except ImportError:
    winreg = None

@(lambda x: x())
def PYVERSIONS():
    url = "https://www.python.org/ftp/python/"
    headers = {'User-Agent': f"kajol/{kajol.__version__}"}

    res = requests.get(url, headers=headers)
    res.raise_for_status()

    html = HTML.parse_dom(res.text)
    pattern = re.compile(r'^(\d+\.\d+(\.\d+)?)/$')

    grouped = {"_flat": set()}
    for a in html.select_all_by_tag_name("a"):
        match = pattern.match(a.text)
        if match:
            version = match[1]
            series = ".".join(version.split(".")[:2])

            grouped["_flat"].add(version)
            grouped.setdefault(series, []).append(version)

    # sort each series numerically
    for series in filter(lambda x: not x.startswith("_"), grouped):
        grouped[series].sort(key=Version)

    grouped["_latest"] = max(grouped["_flat"], key=Version)

    return grouped

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

def add_to_windows_user_path(new_path: str):
    registry_key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, "Environment", 0,
        winreg.KEY_READ | winreg.KEY_WRITE
    )
    try:
        current_path, data_type = winreg.QueryValueEx(registry_key, "Path")
    except FileNotFoundError:
        current_path, data_type = "", winreg.REG_EXPAND_SZ

    if new_path in current_path.split(os.pathsep):
        print("the path already exists in the User PATH.")
        return

    updated_path = f"{current_path};{new_path}".strip(";")
    winreg.SetValueEx(registry_key, "Path", 0, data_type, updated_path)
    winreg.CloseKey(registry_key)

    HWND_BROADCAST, WM_SETTINGCHANGE = 0xFFFF, 0x001A
    ctypes.windll.user32.SendMessageW(
        HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment"
    )
    print("successfully updated user PATH")

def download(url, path):
    res = requests.get(url, stream=True, headers={
        'User-Agent': f"kajol/{kajol.__version__}"
    })

    with open(path, "wb") as f:
        for i, chunk in enumerate(res.iter_content(8192)):
            f.write(chunk)
            maxlen = shutil.get_terminal_size().columns - len("downloading ") \
                     - len(f"... chunk {i}")
            if len(url) > maxlen:
                dispurl = url[:maxlen]
            else:
                dispurl = url
            print(f"\rdownloading {dispurl}... chunk {i}", end="")

    print(f"\r\x1b[2Kfinished downloading {url}")

def _pystand_get_latest_release():
    url = "https://raw.githubusercontent.com/astral-sh/" + \
          "python-build-standalone/latest-release/latest-release.json"
    headers = {'User-Agent': f"kajol/{kajol.__version__}"}
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def tarfile_open(path):
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
    with tarfile_open(str(zip_path)) as tar:
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

def latest_python(version="latest"):
    if version == "latest":
        return PYVERSIONS["_latest"]

    v = Version(version)
    if len(v.release) == 3:  # full version
        return str(v)
    else:  # series only
        series = f"{v.major}.{v.minor}"
        if series not in PYVERSIONS:
            raise RuntimeError("We don't have that type of cheese.")
        return max(PYVERSIONS[series], key=Version)

def _installed_python():
    root = Path.home() / ".kajol" / "python"
    if not root.exists():
        raise FileNotFoundError("no kajol-managed interpreters installed.")
    vdirs = sorted(root.iterdir())
    if not vdirs:
        raise FileNotFoundError("no kajol-managed interpreters installed.")
    for vdir in vdirs:
        if (vdir / ("bin" if os.name != "nt" else "Scripts")).exists():
            yield vdir.name, list((
                vdir / ("bin" if os.name != "nt" else "Scripts")
            ).glob('python*.bat'))

def list_installed_python():
    for version, scripts in _installed_python():
        print(version, "->", [p.name for p in scripts])
#
def uninstall_python(version):
    install_dir = Path.home() / ".kajol" / "python" / version
    if not install_dir.exists():
        raise ValueError(f"Could not find Python {version}. Either it "
                         f"is not installed or it is not managed by "
                         f"kajol.")

    shutil.rmtree(install_dir)
    print("successfully uninstalled Python", version)
#
def _get_latest_installed(version):
    if version is None:
        return max(_installed_python(), key=lambda x: Version(x[0]))

    v = Version(version)
    if len(v.release) == 3:  # full version
        try:
            return filter(
                lambda x: x[0] == version, _installed_python()
            )[0]
        except IndexError as e:
            raise FileNotFoundError(
                f"Python {version} is not installed, use "
                f"kajol install {version} to install it."
            ) from e
    else:  # series only
        series = f"{v.major}.{v.minor}"
        try:
            return max(
                filter(
                    lambda x: x[0].startswith(series), _installed_python()
                ),
                key=lambda x: Version(x[0])
            )
        except ValueError as e:
            raise FileNotFoundError(
                f"Python {version} is not installed, use "
                f"kajol install {version} to install it."
            ) from e

def exec_python(version=None, args=None):
    if not args: args = []
    version, scripts = _get_latest_installed(version)
    return subprocess.run([str(scripts[0]), *args])
#
def list_available_python(*, verbose=False, cmdline=False):
    if verbose:
        print(
            *map(lambda x: f"Python {x}", sorted(
                PYVERSIONS["_flat"], key=Version
            )),
            sep="\n"
        )
    else:
        if cmdline:
            print("use -v to get full list")

        print(
            *map(lambda x: f"Python {x}.*", sorted(
                filter(lambda x: not x.startswith("_"), PYVERSIONS),
                key=Version
            )),
            sep="\n"
        )
#
def shell(version=None):
    def _shell():
        try:
            return shellingham.detect_shell()[1]
        except shellingham.ShellDetectionFailure:
            if os.name == 'posix':
                return os.environ['SHELL']
            elif os.name == 'nt':
                return os.environ['COMSPEC']
            raise NotImplementedError("'Officially unsupported' OS")
    
    version, scripts = _get_latest_installed(version)
    scripts_dir = scripts[0].parent
    
    print("starting a shell with default Python version", version)
    try:
        subprocess.run([shutil.which(_shell())],
            env={
                **os.environ,
                "PATH": f"{scripts_dir}{os.pathsep}{os.environ["PATH"]}"
            }
        )
    except (KeyboardInterrupt, EOFError): pass
    print("goodbye!")