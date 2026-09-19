import re
import requests
import os
import ctypes
import zipfile
import platform
import subprocess
from pathlib import Path
from packaging.version import Version

import kajol
from kajol.install import HTML
from kajol.pyinstall.shared import PYVERSIONS, download, add_to_windows_user_path

# --- Installer picker ---
def get_best_installer(version, auto_retry, allow_exe=False, allow_zip=True):
    if Version(version) < Version("3.10"):
        allow_zip, allow_exe = False, True
    
    url = f"https://www.python.org/ftp/python/{version}/"
    headers = {'User-Agent': f"kajol/{kajol.__version__}"}
    res = requests.get(url, headers=headers)
    res.raise_for_status()

    html = HTML.parse_dom(res.text)
    files = [a.text for a in html.select_all_by_tag_name("a")]

    system = platform.system().lower()
    arch = platform.machine().lower()

    candidates = []

    if system == "windows":
        arch_map = {
            "amd64": "amd64",
            "x86_64": "amd64",
            "arm64": "arm64",
            "aarch64": "arm64",
            "x86": "win32"
        }
        target = arch_map.get(arch, "win32")

        for f in files:
            if f.startswith(f"python-{version}") and (
                (allow_zip and f.endswith(".zip") and "embed" not in f) or \
                (allow_exe and (f.endswith(".exe") or f.endswith(".msi")))
            ):
                if target in f or (target == "win32" and "-win32" in f):
                    # extract the embedded version
                    # (e.g. 3.15.0a8, 3.15.0b4, 3.15.0rc1)
                    m = re.match(r"python-(\d+\.\d+\.\d+\w*)", f)
                    if m:
                        candidates.append(
                            (Version(m.group(1).rstrip("t")), f)
                        )
    elif system == "darwin":
        for f in files:
            if f.startswith(f"python-{version}") and f.endswith(".pkg"):
                m = re.match(r"python-(\d+\.\d+\.\d+\w*)", f)
                if m:
                    candidates.append((Version(m.group(1).rstrip("t")), f))
    else:
        raise FileNotFoundError("We don't have that kind of cheese.")

    if candidates:
        best = max(candidates, key=lambda x: x[0])
        return str(best[0]), url + best[1]

    # fallback retry logic
    if auto_retry:
        if not allow_exe and system == "windows":
            return get_best_installer(version, True, True)

        v = Version(version)
        if v.micro == 0:
            return str(v), None

        prev_v = Version(f"{v.major}.{v.minor}.{v.micro-1}")
        print(f"couldn't find an installer for {v}, trying {prev_v}")
        return get_best_installer(str(prev_v), True, False)
    else:
        return version, None

def install_python_windows(version, auto_retry):
    version, url = get_best_installer(version, auto_retry)
    if not url:
        raise RuntimeError("We don't have that kind of cheese.")

    target_dir = Path.home() / ".kajol" / "python" / version
    target_dir.mkdir(parents=True, exist_ok=True)
    
    if url.endswith(".exe") or url.endswith(".msi"):
        print("Python will be installed via the system installer.")
        print("it will therefore not be managed by kajol.")
        path = target_dir / f"python-{version}.{url.rsplit(".", 1)[1]}"
        download(url, path)
        print("running installer... ", end="", flush=True)
        subprocess.call([path])
        print("done!")
        return

    zip_path = target_dir / f"python-{version}.zip"
    
    download(url, zip_path)

    print("unzipping...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target_dir)
    
    # make "binaries"
    bin_dir = Path(target_dir / ("bin" if os.name != "nt" else "Scripts"))
    bin_dir.mkdir(exist_ok=True)
    
    v = Version(version)
    for x in ("python", f"python{v.major}",
              f"python{v.major}.{v.minor}"):
        script = f"@{target_dir.resolve() / "python.exe"} %*"
        
        with open(bin_dir / (x + ".bat"), "w") as f:
            f.write(script)
    
    for x in ("pythonw", f"pythonw{v.major}",
              f"pythonw{v.major}.{v.minor}"):
        script = f"@{target_dir.resolve() / "pythonw.exe"} %*"
        
        with open(bin_dir / (x + ".bat"), "w") as f:
            f.write(script)

    print(f"Python {version} installed to {target_dir}")
    
    if input("add Python install to PATH? ").lower().startswith("y"):
        add_to_windows_user_path(str(bin_dir))

def install_python_darwin(version, auto_retry):
    version, url = get_best_installer(version, auto_retry)
    if not url:
        raise FileNotFoundError("We don't have that kind of cheese.")

    target_dir = pathlib.Path.home() / ".kajol" / "python" / version
    target_dir.mkdir(parents=True, exist_ok=True)

    pkg_path = target_dir / f"python-{version}.pkg"
    
    download(url, pkg_path)
    subprocess.call(['open', pkg_path])

def install_python(version, auto_retry):
    system = platform.system().lower()
    if system == "windows":
        install_python_windows(version, auto_retry)
    elif system == "darwin":
        print("Python will be installed via the system installer.")
        print("it will therefore not be managed by kajol.")
        install_python_darwin(version, auto_retry)
    else:
        raise FileNotFoundError("We don't have that kind of cheese.")