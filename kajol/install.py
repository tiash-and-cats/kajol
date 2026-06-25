import re
import sys
import sysconfig
import shutil
import html.parser
import collections
import requests
import pathlib
import packaging.tags
import zipfile
import pickle
import io
import os
import stat
from pathlib import Path
from packaging.utils import parse_wheel_filename
from packaging.requirements import Requirement
from packaging.version import Version
from dataclasses import dataclass
from textwrap import dedent
from configparser import ConfigParser

class HTML:    
    @staticmethod
    def parse_dom(html_code):
        parser = HTML._Parser()
        parser.feed(html_code)
        parser.close()
        return parser.root
    
    @dataclass
    class Document:
        children: list
        
        def all_children(self):
            def walk(node):
                result = []
                for child in getattr(node, "children", []):
                    result.append(child)
                    result.extend(walk(child))
                return result
            return walk(self)

    @dataclass
    class Element:
        tag: str
        attrs: dict
        children: list

    @dataclass
    class Text:
        text: str

    @dataclass
    class Comment:
        text: str

    @dataclass
    class ProcessingInstruction:
        target: str
        data: str
        
    class _Parser(html.parser.HTMLParser):
        VOID_TAGS = {"meta", "br", "hr", "img", "input", "link", "source"}
        
        def __init__(self):
            super().__init__()
            self._pending_close = collections.deque()
            self._top_level_nodes = []
            self.root = None

        def handle_starttag(self, tag, attrs):
            elmnt = HTML.Element(tag, dict(attrs), [])
            if tag in self.VOID_TAGS:
                # Void element: close immediately
                if self._pending_close:
                    self._pending_close[-1].children.append(elmnt)
                else:
                    self._top_level_nodes.append(elmnt)
            else:
                self._pending_close.append(elmnt)
        
        def handle_comment(self, data):
            comment = HTML.Comment(data)
            if self._pending_close:
                self._pending_close[-1].children.append(comment)
            else:
                self._top_level_nodes.append(comment)

        def handle_data(self, text):
            if self._pending_close and text.strip():
                self._pending_close[-1].children.append(HTML.Text(text))

        def handle_endtag(self, tag):
            if self._pending_close:
                e = self._pending_close.pop()
                if self._pending_close:
                    self._pending_close[-1].children.append(e)
                else:
                    self._top_level_nodes.append(e)
        
        def handle_pi(self, data):
            # Split manually into target + data if needed
            parts = data.split(maxsplit=1)
            target = parts[0]
            detail = parts[1] if len(parts) > 1 else ""
            pi = HTML.ProcessingInstruction(target, detail)
            if self._pending_close:
                self._pending_close[-1].children.append(pi)
            else:
                self._top_level_nodes.append(pi)

        def close(self):
            super().close()
            if not self.root:
                self.root = HTML.Document(self._top_level_nodes)

def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()

def site_packages(user=False):
    if user:
        return Path(sysconfig.get_path("purelib", "user"))
    else:
        return Path(sysconfig.get_path("purelib"))

supported = set(packaging.tags.sys_tags())

def parse_tags(filename):
    parts = filename.split("-")
    return {packaging.tags.Tag(parts[2], parts[3], parts[4].removesuffix(".whl"))}

def best_wheel(requirement: Requirement):
    # fetch the simple index page
    url = f"https://pypi.org/simple/{normalize(requirement.name)}/"
    html = requests.get(url)
    html.raise_for_status()
    html = html.text

    # extract all links to .whl
    wheels = []
    for a in HTML.parse_dom(html).all_children():
        if isinstance(a, HTML.Element) and a.tag.lower() == "a" \
           and "data-yanked" not in a.attrs:
            for child in a.children:
                if isinstance(child, HTML.Text):
                    fname = child.text.strip()
                    if fname.endswith(".whl"):
                        wheels.append((fname, a.attrs["href"]))

    # get supported tags
    supported = set(packaging.tags.sys_tags())

    # collect all compatible wheels
    compatible = []
    for fname, href in wheels:
        name, version, build, tags = parse_wheel_filename(fname)
        if tags & supported:
            if not requirement.specifier or version in requirement.specifier:
                compatible.append((version, fname, href))

    # pick the latest version among compatible
    if compatible:
        compatible.sort(key=lambda x: x[0], reverse=True)
        latest = compatible[0]
        return latest[1], latest[2].split("#", 1)[0]  # filename, download link

    return None

def is_installed(req, user, where):
    for dist_info in where.glob(f"{normalize(req.name).replace("-", "_")}-*.dist-info"):
        metadata_path = dist_info / "METADATA"
        if metadata_path.exists():
            text = metadata_path.read_text(encoding="utf-8")
            # Extract version line
            for line in text.splitlines():
                if line.startswith("Version: "):
                    installed_version = Version(line.split("Version: ")[1].strip())
                    # Check if requirement specifier allows this version
                    if not req.specifier or installed_version in req.specifier:
                        return True
    return False

def get(pkgspec, user, depnts, deptree, deps, where):
    req = Requirement(pkgspec.strip())
    if not (req.marker is None or req.marker.evaluate()):
        return
    
    if depnts: print()
    
    if is_installed(req, user, where):
        print(f"already installed: {req} {f"(from {" -> ".join(depnts)})" if depnts else ""}")
        return
    
    if not depnts:
        print("getting", req)
    else:
        print("getting", req, "from", " -> ".join(depnts))
    
    content = fname = dload = None
    
    if any(x[0] == req for x in deptree):
        print("    already in deptree, skipping")
        return
    
    if pkgspec.endswith(".whl") and Path(pkgspec).is_file():
        with open(pkgspec, "rb") as f:
            content = f.read()
        
        fname = pkgspec
        dload = None
    else:
        wheel = best_wheel(req)
        
        if not wheel:
            raise FileNotFoundError("no matching .whl file!")
         
        fname, dload = wheel
        
        cache = Path.home() / ".kajol" / "cache"
        cache.mkdir(exist_ok=True, parents=True)
        
        fpath = cache / fname
        if not fpath.exists():
            print("    downloading", fname, "from PyPI")
            response = requests.get(dload)
            with open(fpath, "wb") as f:
                f.write(response.content)
            content = response.content
        else:
            print("    loading", fname, "from cache")
            with open(fpath, "rb") as f:
                content = f.read()
    
    if deps:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            fs = zf.namelist()
            
            if dist_info_folder := next(
                (f for f in fs if f.split('/')[0].endswith('.dist-info')), 
                None
            ):
                folder_prefix = dist_info_folder.split('/')[0]
                metadata_path = f"{folder_prefix}/METADATA"
                
                try:
                    metadata_bytes = zf.read(metadata_path)
                    metadata_text = metadata_bytes.decode("utf-8")
                    
                    deps = [
                        x.removeprefix("Requires-Dist: ") 
                        for x in metadata_text.split("\n") 
                        if x.startswith("Requires-Dist: ")
                    ]
                    for dep in deps:
                        get(dep, user, depnts + (str(req),), deptree, True, where)
                except KeyError:
                    raise FileNotFoundError(f"could not find {wheel}/{folder_prefix}/METADATA")
    
    deptree.add((req, fname, dload))

BAR = chr(9608)

def progress_bar(txt, progress, total):
    """
    Based on Progress Bar Simulation, by Al Sweigart al@inventwithpython.com
    available at https://nostarch.com/big-book-small-python-programming
    """
    bar = ''  # The progress bar will be a string value.
    bar += '['  # Create the left end of the progress bar.

    # Make sure that the amount of progress is between 0 and total:
    if progress > total:
        progress = total
    if progress < 0:
        progress = 0

    # Calculate the number of "bars" to display:
    bars = int((progress / total) * 30)

    bar += BAR * bars  # Add the progress bar.
    bar += ' ' * (30 - bars)  # Add empty space.
    bar += ']'  # Add the right end of the progress bar.

    # Calculate the percentage complete:
    pcent = round(progress / total * 100, 1)
    bar += ' ' + str(pcent).rjust(5) + '%'  # Add percentage.

    # Add the numbers:
    bar += ' ' + str(progress) + '/' + str(total)

    print("\r\x1b[2K" + txt.ljust(50) + bar, end="")

def add_executable_bit(filepath):
    current_permissions = os.stat(filepath).st_mode
    executable_bits = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    new_permissions = current_permissions | executable_bits
    os.chmod(filepath, new_permissions)

def install(pkgspecs=None, *, user=False, deps=True, where=None, no_lock=False):
    if not where:
        where = site_packages()
    
    where.mkdir(exist_ok=True, parents=True)
    
    if not pkgspecs:
        deps = False
        with open("kajol.lock.pkl", "rb") as f:
            pkgspecs = pickle.load(f)
    
    deptree = set()
    for pkgspec in pkgspecs:
        get(pkgspec, user, (), deptree, deps, where)
        print()
    
    conf = ConfigParser()
    
    for i, dep in enumerate(deptree):
        req, fname, dload = dep
        progress_bar(f"installing {req.name}", i, len(deptree))
        
        if dload: # on an index
            cache = Path.home() / ".kajol" / "cache"
            fpath = cache / fname
            content = None
            if not fpath.exists():
                response = requests.get(dload)
                with open(fpath, "wb") as f:
                    f.write(response.content)
                content = response.content
            else:
                with open(fpath, "rb") as f:
                    content = f.read()
        else: # local
            with open(fname, "rb") as f:
                content = f.read()
                
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            fs = zf.namelist()
            
            if dist_info_folder := next(
                (f for f in fs if f.split('/')[0].endswith('.dist-info')), 
                None
            ):
                try:
                    folder_prefix = dist_info_folder.split('/')[0]
                    text = zf.read(f"{folder_prefix}/entry_points.txt") \
                           .decode("utf-8")
                    conf.read_string(text)
                    entries = conf["console_scripts"]
                    for ex, fn in entries.items():
                        mod, fn = fn.split(":", 1)
                        
                        if os.name == "nt":
                            with open(
                                Path(sysconfig.get_path("scripts")) / 
                                (ex + ".bat"), "w"
                            ) as f:
                                f.write(
                                    f'@{sys.executable} "-cimport sys as b,'
                                    f'{mod} as a;b.argv[0]=r\'%0\';exit(a.{fn}'
                                    f'())" %*'
                                )
                        else:
                            with open(
                                Path(sysconfig.get_path("scripts")) / ex, "w"
                            ) as f:
                                f.write(dedent(f"""
                                    #!{sys.executable}
                                    import sys
                                    from {mod} import {fn}
                                    if __name__ == "__main__":
                                        sys.exit({fn}())
                                """))
                            add_executable_bit(
                                Path(sysconfig.get_path("scripts")) / ex
                            )
                except KeyError:
                    pass # no entry_points.txt? fine!
                
            zf.extractall(where)
    
    print(f"\r\x1b[2Kfinished installing: {
        ", ".join([dep[0].name for dep in deptree]) if deptree else "(none)"
    }")
    
    if not no_lock:
        lockfile = Path("kajol.lock.pkl")
        if lockfile.is_file():
            with lockfile.open("rb") as f:
                lock = set(pickle.load(f))
        else:
            lock = set()
        lock.update([str(x[0]) for x in deptree])
        with lockfile.open("wb") as f:
            pickle.dump(lock, f)

def uninstall(pkgname, *, user=False, yes=False):
    sp = site_packages(user)
    dist_infos = list(sp.glob(f"{normalize(pkgname).replace("-", "_")}-*.dist-info"))
    if not dist_infos:
        print(f"{pkgname} is not installed")
        return

    if not yes and not input(f"are you sure you want to uninstall {pkgname}? ") == "y":
        return
        
    conf = ConfigParser()
        
    for dist_info in dist_infos:
        if (entry_points_path := dist_info / "entry_points.txt").is_file():
            conf.read(entry_points_path)
            if "console_scripts" in conf:
                entries = conf["console_scripts"]
                for ex, _ in entries.items():
                    if os.name == "nt":
                        try:
                            os.remove(
                                Path(sysconfig.get_path("scripts")) / 
                                (ex + ".bat")
                            )
                        except:
                            try:
                                os.remove(
                                    Path(sysconfig.get_path("scripts")) / 
                                    (ex + ".exe")
                                )
                            except: pass
                    else:
                        try:
                            os.remove(
                                Path(sysconfig.get_path("scripts")) / ex, "w"
                            )
                        except: pass
        
        record_path = dist_info / "RECORD"
        if record_path.exists():
            lines = record_path.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines):
                parts = line.split(",")
                if not parts or not parts[0]:
                    continue
                relpath = parts[0]
                target = sp / relpath
                progress_bar(f"uninstalling {pkgname}", i, len(lines))
                if target.exists():
                    try:
                        os.remove(target)
                    except IsADirectoryError:
                        shutil.rmtree(target, ignore_errors=True)
            # remove dist-info itself
            shutil.rmtree(dist_info, ignore_errors=True)
            print(f"\r\x1b[2Kfinished uninstalling {pkgname}")
        else:
            print(f"no RECORD file found in {dist_info}, skipping")
    
    lockfile = Path("kajol.lock.pkl")
    if lockfile.is_file():
        with lockfile.open("rb") as f:
            lock = set(pickle.load(f))
    else:
        lock = set()
    for x in list(filter(lambda y: Requirement(y).name == pkgname, lock)):
        lock.discard(x)
    with lockfile.open("wb") as f:
        pickle.dump(lock, f)

def is_pycache(path):
    return path.is_dir() and path.name == "__pycache__"

def in_pycache(path):
    return any(parent.name == "__pycache__" for parent in path.parents)

def sp_cleanup_empty_dirs(*, user=False):
    print("removing toplevel empty dirs in site-packages... ", end="")
    sp = site_packages(user)
    for d in os.listdir(sp):
        full = Path(sp) / d
        if not full.is_dir():
            continue
        try:
            # If directory has no entries other than __pycache__ 
            # (even if __pycache__ has .pyc files), remove it
            if not any(
                x for x in full.iterdir()
                if not (in_pycache(x) or is_pycache(x))
            ):
                shutil.rmtree(full, ignore_errors=True)
        except FileNotFoundError:
            pass
    print("done")