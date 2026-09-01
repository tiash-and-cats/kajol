import shellingham
import subprocess
import requests
import ctypes
import shutil
import re
import os
from pathlib import Path
from packaging.version import Version

import kajol
from kajol.install import HTML

try:
    import winreg
except ModuleNotFoundError:
    winreg = None

@(lambda x: x())
def PYVERSIONS():
    url = "https://www.python.org/ftp/python/"
    headers = {'User-Agent': f"kajol/{kajol.__version__}"}

    res = requests.get(url, headers=headers)
    res.raise_for_status()

    html = HTML.parse_dom(res.text)
    pattern = re.compile(r'^(\d+\.\d+(\.\d+)?)/$')

    grouped = {"_flat": {"1.3.0"}, "1.3": ["1.3.0"]}
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
#
def _installed_python():
    root = Path.home() / ".kajol" / "python"
    if not root.exists():
        raise FileNotFoundError("no kajol-managed interpreters installed.")
    vdirs = sorted(root.iterdir())
    if not vdirs:
        raise FileNotFoundError("no kajol-managed interpreters installed.")
    for vdir in vdirs:
        if (vdir / "bin").exists():
            yield vdir.name, list((vdir / "bin").glob('python*'))
        elif (vdir / "Scripts").exists():
            yield vdir.name, list((vdir / "Scripts").glob('python*'))

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