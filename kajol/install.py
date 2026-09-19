import re
import sys
import sysconfig
import shutil
import html.parser
import collections
import requests
import pathlib
import packaging.tags
import tempfile
import zipfile
import tarfile
import pickle
import io
import os
import stat
from pathlib import Path
from packaging.utils import parse_wheel_filename
from packaging.requirements import Requirement
from packaging.version import Version
from packaging.markers import default_environment
from dataclasses import dataclass
from textwrap import dedent
from configparser import ConfigParser

from kajol.shared import progress_bar

from build import ProjectBuilder
from build.env import DefaultIsolatedEnv

SUPPORTED = set(packaging.tags.sys_tags())
SCRIPTS_DIR = Path(sysconfig.get_path("scripts"))

if hasattr(sys, 'real_prefix') or (sys.base_prefix != sys.prefix):
    # inside a virtual environment (venv/virtualenv)
    scheme = "posix_prefix" if sys.platform != "win32" else "nt"
else:
    # using global system/user paths
    scheme = sysconfig.get_default_scheme()

DATA_PATHS = {
    k: Path(v) for k, v in sysconfig.get_paths(scheme=scheme).items()
}
DATA_PATHS["headers"] = DATA_PATHS["include"]

class HTML:
    class BaseNode: pass

    class ParentNode(BaseNode):
        def all_children(self):
            def walk(node):
                for child in getattr(node, "children", []):
                    yield child
                    yield from walk(child)
            return walk(self)

        def __iter__(self):
            return iter(self.children)

    @dataclass
    class Document(ParentNode):
        children: list

        def select_all_by_tag_name(self, tag_name):
            return filter(
                lambda e: getattr(e, "tag", None) == tag_name, 
                self.all_children()
            )

    @dataclass
    class Element(ParentNode):
        tag: str
        attrs: dict
        children: list
        
        @property
        def text(self):
            return "".join(
                child.text for child in self.all_children()
                if isinstance(child, HTML.Text)
            )

        def __getitem__(self, k):
            return self.attrs[k]

        def __setitem__(self, k, v):
            self.attrs[k] = v

    @dataclass
    class Text(BaseNode):
        text: str

    @dataclass
    class Comment(BaseNode):
        text: str

    @dataclass
    class ProcessingInstruction(BaseNode):
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

    @staticmethod
    def parse_dom(html_code):
        parser = HTML._Parser()
        parser.feed(html_code)
        parser.close()
        return parser.root

def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()

def site_packages(user=False):
    if user:
        return Path(sysconfig.get_path("purelib", "user"))
    else:
        return Path(sysconfig.get_path("purelib"))

def parse_tags(filename):
    parts = filename.split("-")
    return {packaging.tags.Tag(parts[2], parts[3], parts[4].removesuffix(".whl"))}

def _get_cached_response(url, _cache={}):
    if url in _cache:
        return _cache[url]
    else:
        html = requests.get(url)
        html.raise_for_status()
        return html.text

def best_wheel(requirement: Requirement):
    # fetch the simple index page
    url = f"https://pypi.org/simple/{normalize(requirement.name)}/"
    html = _get_cached_response(url)

    # extract all links to .whl
    wheels = []
    for a in filter(
        lambda a: "data-yanked" not in a.attrs,
        HTML.parse_dom(html).select_all_by_tag_name("a")
    ):
        for child in a.children:
            if isinstance(child, HTML.Text):
                fname = child.text.strip()
                if fname.endswith(".whl"):
                    wheels.append((fname, a.attrs["href"]))
                    break

    # get supported tags
    SUPPORTED = set(packaging.tags.sys_tags())

    # collect all compatible wheels
    compatible = []
    for fname, href in wheels:
        name, version, build, tags = parse_wheel_filename(fname)
        if tags & SUPPORTED:
            if not requirement.specifier or version in requirement.specifier:
                compatible.append((version, fname, href))

    # pick the latest version among compatible
    if compatible:
        compatible.sort(key=lambda x: x[0], reverse=True)
        latest = compatible[0]
        return latest[1], latest[2].split("#", 1)[0]  # filename, download link

    return None

def best_sdist(requirement: Requirement):
    # fetch the simple index page
    url = f"https://pypi.org/simple/{normalize(requirement.name)}/"
    html = _get_cached_response(url)

    # extract all links to sdists
    sdists = []
    for a in filter(
        lambda a: "data-yanked" not in a.attrs,
        HTML.parse_dom(html).select_all_by_tag_name("a")
    ):
        for child in a.children:
            if isinstance(child, HTML.Text):
                fname = child.text.strip()
                if fname.endswith((".tar.gz", ".zip")):
                    sdists.append((fname, a.attrs["href"]))
                    break

    # pick the latest version among sdists that match the specifier
    compatible = []
    for fname, href in sdists:
        # crude version parsing: strip extension and split
        version_str = fname.split("-", 1)[1] \
            .removesuffix(".tar.gz").removesuffix(".zip")
            
        version = Version(version_str)
        if not requirement.specifier or version in requirement.specifier:
            compatible.append((version, fname, href))

    if compatible:
        compatible.sort(key=lambda x: x[0], reverse=True)
        latest = compatible[0]
        return latest[1], latest[2].split("#", 1)[0]  # filename, download link

    return None

def is_installed(req, user, where):
    for dist_info in where.glob(
        f"{normalize(req.name).replace("-", "_")}-*.dist-info"
    ):
        metadata_path = dist_info / "METADATA"
        if metadata_path.exists():
            text = metadata_path.read_text(encoding="utf-8")
            # Extract version line
            for line in text.splitlines():
                if line.startswith("Version: "):
                    installed_version = Version(
                        line.split("Version: ")[1].strip()
                    )
                    # Check if requirement specifier allows this version
                    if not req.specifier or \
                       installed_version in req.specifier:
                        return True
    return False

def find_either_file(start_dir, file_a, file_b):
    for root, dirs, files in os.walk(start_dir):
        for file in files:
            if file == file_a:
                return os.path.join(root, file)
            elif file == file_b:
                return os.path.join(root, file)
    return None, None

def build_from_sdist(fname, dload):
    print("    downloading", fname, "sdist from PyPI")
    response = requests.get(dload)
    response.raise_for_status()

    with tempfile.TemporaryDirectory() as tmpdir:        
        sdist_path = Path(tmpdir) / fname
        with open(sdist_path, "wb") as f:
            f.write(response.content)

        # unpack
        unpack_dir = Path(tmpdir) / "src"
        unpack_dir.mkdir()
        if fname.endswith(".tar.gz"):
            with tarfile.open(sdist_path, "r:gz") as tf:
                tf.extractall(unpack_dir)
        elif fname.endswith(".zip"):
            with zipfile.ZipFile(sdist_path) as zf:
                zf.extractall(unpack_dir)

        # build wheel
        with DefaultIsolatedEnv() as env:
            path = Path(
                find_either_file(unpack_dir, "pyproject.toml", "setup.py")
            ).parent
            
            builder = ProjectBuilder.from_isolated_env(env, str(path))
            
            print("    installing requirements to build wheel")
            env.install(builder.build_system_requires)
            env.install(builder.get_requires_for_build("wheel"))
            
            print("    building to temp wheel")
            built_path = builder.build("wheel", Path(tempfile.gettempdir()))
            
        wheel_path = Path(built_path)
        content = wheel_path.read_bytes()
        return content, wheel_path

def find_cached_wheel(requirement: Requirement, cache: Path):
    for wheel in cache.glob("*.whl"):
        try:
            name, version, build, tags = parse_wheel_filename(wheel.name)
        except Exception:
            continue
        if name == requirement.name:
            if not requirement.specifier or version in requirement.specifier:
                return wheel
    return None

def get(pkgspec, user, depnts, deptree, deps, where, parent):
    req = Requirement(pkgspec.strip())
    
    if req.marker is not None:
        # fetch the baseline environment variables (OS, python_version, etc.)
        base_env = default_environment()
        
        if not parent:
            # no parent extras means 'extra' is empty in this context
            base_env["extra"] = ""
            is_applicable = req.marker.evaluate(base_env)
        else:
            # parent has extras, see if ANY of them satisfy the marker
            is_applicable = False
            for extra in parent.extras:
                # merge the specific extra into a copy of the base environment
                env_copy = base_env.copy()
                env_copy["extra"] = extra
                if req.marker.evaluate(env_copy):
                    is_applicable = True
                    break
                    
        if not is_applicable:
            return

    if depnts: print()

    if is_installed(req, user, where):
        print(f"already installed: {req} {
            f"(from {" -> ".join(depnts)})" if depnts else ""
        }")
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

        fpath = pkgspec
        print("    loading", pkgspec, "from file")
    else:
        wheel = best_wheel(req)

        if not wheel:
            sdist = best_sdist(req)
            if not sdist:
                raise FileNotFoundError("no matching .whl or sdist!")
            fname, dload = sdist
            
            content, fpath = build_from_sdist(fname, dload)
        else:
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
                        get(dep, user, depnts + (str(req),),
                            deptree, True, where, req)
                            
                except KeyError:
                    raise FileNotFoundError(
                        f"could not find {wheel}/{folder_prefix}/METADATA")

    deptree.add((req, content))

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
        get(pkgspec, user, (), deptree, deps, where, None)
        print()

    conf = ConfigParser()

    for i, dep in enumerate(deptree):
        req, content = dep
        progress_bar(f"installing {req.name}", i, len(deptree))

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
                                SCRIPTS_DIR /
                                (ex + ".bat"), "w"
                            ) as f:
                                f.write(
                                    f'@{sys.executable} "-cimport sys as b,'
                                    f'{mod} as a;b.argv[0]=r\'%0\';exit(a.{fn}'
                                    f'())" %*'
                                )
                        else:
                            with open(
                                SCRIPTS_DIR / ex, "w"
                            ) as f:
                                f.write(dedent(f"""
                                    #!{sys.executable}
                                    import sys
                                    from {mod} import {fn}
                                    if __name__ == "__main__":
                                        sys.exit({fn}())
                                """))
                            add_executable_bit(
                                SCRIPTS_DIR / ex
                            )
                except KeyError:
                    pass # no entry_points.txt? fine!

            if data_folder := next(
                (f for f in fs if f.split('/')[0].endswith('.data')),
                None
            ):
                folder_prefix = data_folder.split('/')[0]
                for f in fs:
                    if not f.startswith(folder_prefix + "/"):
                        continue
                    parts = f.split("/", 2)
                    if len(parts) < 2:
                        continue
                    subdir = parts[1]  # e.g. "scripts", "purelib", "headers"
                    target = DATA_PATHS.get(subdir)
                    if target:
                        relpath = parts[2] if len(parts) > 2 else ""
                        dest = target / relpath
                        if f.endswith("/"):
                            dest.mkdir(parents=True, exist_ok=True)
                        else:
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(f) as src, open(dest, "wb") as out:
                                shutil.copyfileobj(src, out)

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
                                SCRIPTS_DIR /
                                (ex + ".bat")
                            )
                        except:
                            try:
                                os.remove(
                                    SCRIPTS_DIR /
                                    (ex + ".exe")
                                )
                            except: pass
                    else:
                        try:
                            os.remove(
                                SCRIPTS_DIR / ex, "w"
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