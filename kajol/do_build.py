import sys
import sysconfig
import subprocess
import importlib.util
import sysconfig
import fnmatch
import pickle
import zipfile
import tomllib
from pprint import pprint
from pathlib import Path
from configparser import ConfigParser as IniParser
import shutil

from kajol.build import *
from kajol.install import install

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

    print("$", " ".join(map(str, cmd)))
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
    with open("kajol.config.py", "w") as f:
        print("from kajol.build import *", file=f)
        print(file=f)
        print("conf = ", end="", file=f)
        pprint(Config(Path.cwd().name, "Eric Idle", "0.0.0"), stream=f)
    print("a kajol.config.py has been generated")
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
    for wheel in build(True):
        os.rename(wheel, Path(output_directory) / wheel)

def build(no_lock=False):
    try:
        conf = load_module_from_file("kajol.__loaded_config__", "kajol.config.py").conf
    except ModuleNotFoundError:
        if Path("pyproject.toml").is_file():
            with open("pyproject.toml") as f:
                pyproject = tomllib.load(f)
            
            assert "project" in pyproject, "pyproject.toml needs a [project]" \
                                           "table"
            project = pyproject["project"]
            
            kajol_config = pyproject.get("tool", {}).get("kajol", {})
            
            if "dynamic" in project and "dependencies" in project["dynamic"]:
                no_lock = False
            
            conf = Config(
                name=project["name"],
                author=project.get("authors", {"name":"Eric Idle"})[0]["name"],
                version=project["version"],
                summary=project.get("description", ""),
                readme=project.get("readme", "README.md"),
                license=project.get("license", "MIT"),
                classifiers=project.get("classifiers", []),
                build=BuildConfig(
                    extensions=map(
                        lambda d: Extension(**d), 
                        kajol_config.get("c_exts", [])
                    ),
                    ignore=kajol_config.get("ignore", []),
                    deps=project.get("dependencies", []),
                    vendor_dir=kajol_config.get("vendor_dir"),
                    entry_pts=project.get("scripts", {})
                )
            )
        else:
            raise FileNotFoundError("config file not found: couldn't find a"
                                    "kajol.config.py or pyproject.toml!")
    
    build_dir = Path("./build") / wheel_tags()
    shutil.rmtree(build_dir, ignore_errors=True)
    build_dir.mkdir(parents=True)
    
    print("building to", build_dir)

    # compile extensions
    if conf.build.extensions:
        print("compiling conf.build.extensions\n")
        for ext in conf.build.extensions:
            compile_c(ext.files, ext.output)
    
    conf.build.ignore = [
        "*.whl", "kajol.lock.pkl", "kajol.config.py", *conf.build.ignore
    ]
        
    record = []
    
    deps = []
    if Path("kajol.lock.pkl").is_file() and not no_lock:
        with open("kajol.lock.pkl", "rb") as lockfile:
            deps.extend(pickle.load(lockfile))
    deps.extend(conf.build.deps)

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
            record.append(str(file_path))
            shutil.copy2(file_path, dest)
    
    print("\ncopied files")
    
    if conf.build.vendor_dir:
        print("vendoring deps\n")
        install(deps, where=build_dir / conf.build.vendor_dir, no_lock=True)
        with open(build_dir / f"_{conf.name}_vendor.pth", "w") as f:
            f.write(str(conf.build.vendor_dir))
    
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
        if not conf.build.vendor_dir:
            for x in deps:
                print("Requires-Dist:", x, file=f)
        print(file=f)
        with open(conf.readme) as readme:
            shutil.copyfileobj(readme, f)
    
    with open(dist_info / "WHEEL", "w") as f:
        print("Wheel-Version: 1.0", file=f)
        print("Generator:", "kajol.do_build", file=f)
        print(
            "Root-Is-Purelib:", str(not bool(conf.build.extensions)).lower(),
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
    with zipfile.ZipFile(wheel, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file_path in build_dir.rglob("*"):
            if file_path.is_file():
                rel = file_path.relative_to(build_dir)
                zipf.write(file_path, rel)
    
    wheels = [wheel]
    
    print("successfully built a wheel:", wheel)
    
    if not conf.build.extensions:
        wheel_pure = Path(
            f"{conf.name}-{conf.version}-{wheel_tags_pure()}.whl"
        ).resolve()
        shutil.copy(wheel, wheel_pure)
        wheels.append(wheel_pure)
    
    return wheels