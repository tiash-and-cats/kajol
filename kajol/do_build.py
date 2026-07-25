import sys
import sysconfig
import subprocess
import importlib.util
import sysconfig
import fnmatch
import pickle
import zipfile
import tomlkit as tomllib
import os
from pprint import pprint
from pathlib import Path
from configparser import ConfigParser as IniParser
import shutil

from kajol.build import *
from kajol.install import install, progress_bar

def compile_c(files, out):
    gcc = shutil.which("gcc")
    if not gcc:
        raise RuntimeError("gcc not found in PATH")

    # Get Python build configuration
    include_dir = sysconfig.get_paths()["include"]
    lib_dir = sysconfig.get_config_var("LIBDIR")
    ext_suffix = sysconfig.get_config_var("EXT_SUFFIX")
    lib_name = f"python{sys.version_info.major}{sys.version_info.minor}"

    # Ensure output has correct suffix
    if not out.endswith(ext_suffix):
        out = out + ext_suffix

    cmd = [
        gcc,
        "-shared",
        "-fPIC",  # needed on Unix
        "-I", include_dir,
        "-L", lib_dir,
        *files,
        f"-l{lib_name}",
        "-o", str(out)
    ]

    print("    $", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True)
    return Path(out)

def load_module_from_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def wheel_tags():
    py_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    plat_tag = sysconfig.get_platform().replace("-", "_").replace(".", "_")
    return f"{py_tag}-{py_tag}-{plat_tag}"

def wheel_tags_pure():
    py_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    return f"{py_tag}-none-any"

def init():
    with open("pyproject.toml", "w") as f:
        f.write(Config(Path.cwd().name, "Eric Idle", "0.0.0").pyproject())
    print("a pyproject.toml has been generated")
    with open("README.md", "w") as f:
        print("#", Path.cwd().name, file=f)
        print(file=f)
        print("These are the docs for", Path.cwd().name, file=f)
    print("a README.md has been generated")

def is_inside(path, parent):
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False

def build_wheel(output_directory, config_settings=None, metadata_directory=None):
    Path(output_directory).mkdir(exist_ok=True)
    wheels = build(True, True)
    for wheel in wheels:
        os.rename(wheel, Path(output_directory) / wheel)
    return str(Path(output_directory) / wheels[-1])

def build(no_lock=False, force_pyproject=False):
    try:
        if force_pyproject: raise FileNotFoundError
        conf = load_module_from_file(
            "kajol.__loaded_config__", "kajol.config.py"
        ).conf
    except FileNotFoundError:
        if Path("pyproject.toml").is_file():
            with open("pyproject.toml") as f:
                conf = Config.from_pyproject(f.read())
        else:
            raise FileNotFoundError(
                "config file not found: couldn't find a" + 
                ("kajol.config.py or " if not force_pyproject else "") + 
                "pyproject.toml!"
            )
    
    build_dir = Path("./build") / wheel_tags()
    shutil.rmtree(build_dir, ignore_errors=True)
    build_dir.mkdir(parents=True)
    
    print("building to", build_dir)
    
    conf.build.ignore = [
        "*.whl", "kajol.config.py", "kajol.lock.pkl", *conf.build.ignore
    ]
        
    record = []
    
    deps = []
    if conf.build.deps:
        deps = conf.build.deps
    elif Path("kajol.lock.pkl").is_file() and not no_lock:
        with open("kajol.lock.pkl", "rb") as lockfile:
            deps = pickle.load(lockfile)
        print("found dependencies from lockfile:", *deps)
        if not input("are these correct? ").lower().startswith("y"):
            deps = []

    # compile extensions
    if conf.build.extensions:
        print("\n======= compiling C extensions")
        for ext in conf.build.extensions:
            compile_c(ext.files, ext.output)
        print("======= finished compiling C extensions\n")

    # copy project files into stage_dir, excluding ignores
    source_dir = Path.cwd().resolve()
    for file_path in source_dir.rglob("*"):
        if is_inside(file_path, build_dir): continue
        if file_path.is_file():
            rel = file_path.relative_to(source_dir)

            # skip ignored patterns
            if any(fnmatch.fnmatch(str(rel), pat) for pat in \
                   conf.build.ignore):
                continue

            dest = build_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            record.append(str(rel))
            shutil.copy2(file_path, dest)
    
    print("copied files")
    
    if conf.build.vendor:
        print("\n======= vendoring dependencies")
        install(deps, where=build_dir / conf.build.vendor.pkg_dir, 
                no_lock=True)
        with open(build_dir / conf.build.vendor.pth_file, "w") as f:
            f.write(str(conf.build.vendor.pkg_dir))
        print("======= finished vendoring dependencies")
    
    dist_info = build_dir / \
        f"{conf.name}-{conf.version}.dist-info"
    dist_info.mkdir(parents=True, exist_ok=True)
    
    with open(dist_info / "RECORD", "w") as f:
        f.write("\n".join(record))
    
    with open(dist_info / "METADATA", "w") as f:
        print("Metadata-Version: 2.4", file=f)
        print("Name:", conf.name, file=f)
        print("Version:", conf.version, file=f)
        print("Summary:", conf.summary, file=f)
        print("License:", conf.license, file=f)
        for x in conf.classifiers:
            print("Classifier:", x, file=f)
        if not conf.build.vendor:
            for x in deps:
                print("Requires-Dist:", x, file=f)
        print(file=f)
        with open(conf.readme) as readme:
            shutil.copyfileobj(readme, f)
    
    with open(dist_info / "WHEEL", "w") as f:
        print("Wheel-Version: 1.0", file=f)
        print("Generator:", "kajol.do_build", file=f)
        print(
            "Root-Is-Purelib:", str(not conf.build.extensions).lower(),
            file=f
        )
        print("Tag:", wheel_tags(), file=f)
        print(file=f)
        print(file=f)
    
    if conf.build.entry_pts:
        with open(dist_info / "entry_points.txt", "w") as f:
            ini = IniParser()
            ini["console_scripts"] = conf.build.entry_pts
            ini.write(f)
    
    print("\ncreated", dist_info)

    # build wheel filename
    wheel = Path(
        f"{conf.name}-{conf.version}-{wheel_tags()}.whl"
    ).resolve()

    # compress staged contents into wheel
    with zipfile.ZipFile(wheel, "w", zipfile.ZIP_DEFLATED) as zf:
        files = list(build_dir.rglob("*"))
        for i, file_path in enumerate(files):
            if file_path.is_file():
                rel = file_path.relative_to(build_dir)
                zf.write(file_path, rel)
                progress_bar(f"creating wheel: {wheel.name}", i, len(files))
    
    wheels = [wheel]
    
    print("\r\x1b[2Ksuccessfully built:", wheel)
    
    return wheels