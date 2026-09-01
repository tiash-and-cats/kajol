import subprocess
import textwrap
import requests
import zipfile
import tarfile
import shutil
import sys
import io
from pathlib import Path
from packaging.version import Version

import kajol
from kajol.install import HTML
from kajol.pyinstall.shared import (PYVERSIONS, download, latest_python, 
                                    add_to_windows_user_path)

def _py13():
    target_dir = Path.home() / ".kajol" / "python" / "1.3.0"
    target_dir.mkdir(parents=True, exist_ok=True)
    
    if sys.platform == "win32":
        url = "https://www.python.org/ftp/python/binaries-1.3/pythonwin.zip"

        zip_path = target_dir / "pythonwin.zip"
        download(url, zip_path)
        
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(target_dir)
        
        bin_dir = Path(target_dir / "bin")
        bin_dir.mkdir(exist_ok=True)
        
        for x in ("python", "python1", "python1.3"):
            script = textwrap.dedent(f"""
                @echo off
                setlocal
                set PYTHONPATH=.;{target_dir / "scripts"};\
{target_dir / "lib"};{target_dir / "sockets"};{target_dir}
                {target_dir.resolve() / 'Python.exe'} %*
                endlocal
            """)
            with open(bin_dir / (x + ".bat"), "w") as f:
                f.write(script)
        
        if input("add Python install to PATH? ").lower().startswith("y"):
            add_to_windows_user_path(str(bin_dir))
    elif platform.system() == "Linux":
        if not shutil.which("make"):
            raise FileNotFoundError(
                "need make to install Python 1.3 on Linux"
            )
        
        print("please note that Python 1.3 will be installed via the")
        print("Makefile, which means kajol will not be able to ")
        print("manage it.")
        
        url = \
          "https://www.python.org/ftp/python/binaries-1.3/python-linux.tar.gz"
        headers = {'User-Agent': f"kajol/{kajol.__version__}"}
        res = requests.get(url, headers=headers)
        res.raise_for_status()

        zip_path = target_dir / "python-linux.tar.gz"
        download(url, zip_path)
        
        with tarfile.TarFile(zip_path) as zf:
            zf.extractall(target_dir)
        
        subprocess.run([
            shutil.which("make"), "install-elf-static"
        ], cwd=str(target_dir))
        
        shutil.rmtree(target_dir)
    else:
        raise FileNotFoundError("We don't have that kind of cheese. "
                                "(Python 1.3.0 only has binaries for Windows "
                                "and Linux)")
#
def _py091():
    target_dir = Path.home() / ".kajol" / "python" / "0.9.1"
    target_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_latest_release():
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
            'User-Agent': f"kajol/{kajol.__version__}"
        }
        url = "https://api.github.com/repos/tiash-and-cats/py0.9.1-win32/" \
              "releases/latest"
        response = requests.get(url, headers=headers)
        return response.json()
    
    if sys.platform == "win32":
        url = _get_latest_release()["assets"][0]["browser_download_url"]
        
        res = requests.get(url, headers={
            'User-Agent': f"kajol/{kajol.__version__}"
        })
        res.raise_for_status()

        zip_path = target_dir / "python.zip"
        download(url, zip_path)
        
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(target_dir)
        
        bin_dir = Path(target_dir / "bin")
        
        for x in ("python", "python0", "python0.9"):
            script = textwrap.dedent(f"""
                @echo off
                setlocal
                set PYTHONPATH=.;{target_dir / "lib"}
                {bin_dir.resolve() / 'python.exe'} %*
                endlocal
            """)
            with open(bin_dir / (x + ".bat"), "w") as f:
                f.write(script)
        
        if input("add Python install to PATH? ").lower().startswith("y"):
            add_to_windows_user_path(str(bin_dir))
    else:
        raise FileNotFoundError("We don't have that kind of cheese. "
                                "(We don't have Python 0.9.1 binaries for "
                                "systems other than Windows)")
#
_FMAP = {
    "1.3.0": _py13,
    "0.9.1": _py091
}

PYVERSIONS.update({".".join(v.split(".")[:2]): [v] for v in _FMAP})
PYVERSIONS["_flat"].update(list(_FMAP))

def install_python(version, _):
    version = latest_python(version)
    
    if version not in _FMAP:
        raise FileNotFoundError("We don't have that kind of cheese.")
    
    print("installing Python", version)
    
    _FMAP[version]()