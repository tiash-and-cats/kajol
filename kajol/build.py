import kajol
import tomlkit
from dataclasses import dataclass, field

@dataclass
class Extension:
    files: list[str]
    output: str | None = None
    
    def toml(self):
        return {"files": self.files, "output": self.output}

@dataclass
class VendorConfig:
    pth_file: str
    pkg_dir: str

@dataclass
class BuildConfig:
    ignore: list[str] = field(default_factory=list)
    deps: list[str] = field(default_factory=list)
    
    entry_pts: dict[str, str] = field(default_factory=dict)
    extensions: list[Extension] = field(default_factory=list)
    
    vendor: VendorConfig | None = None
    compileall: bool = False

@dataclass
class Author:
    name: str
    email: str = None

    def __post_init__(self):
        if self.email is None:
            self.email = f"{
                "".join(map(str.lower, self.name.split()))
            }@example.com"
    
    def toml(self):
        return {"name": self.name, "email": self.email}

@dataclass
class Config:
    name: str
    author: str # backwards compatibility
    version: str
    summary: str = ""
    readme: str = "README.md"
    license: str = "MIT"
    classifiers: list[str] = field(default_factory=list)
    build: BuildConfig = field(default_factory=BuildConfig)
    authors: list[Author] = field(default_factory=list)
    
    def __post_init__(self):
        if isinstance(self.author, str):
            self.authors = [Author(self.author)]
    
    @staticmethod
    def from_pyproject(toml_str):
        pyproject = tomlkit.loads(toml_str)
        
        assert "project" in pyproject, "pyproject.toml needs a [project]" \
                               "table"
        project = pyproject["project"]
        
        kajol_config = pyproject.get("tool", {}).get("kajol", {})
        
        if "dynamic" in project and "dependencies" in project["dynamic"]:
            no_lock = False
        
        authors = [Author(**d) for d in project.get("authors", [])]
        
        c = Config(
            name=project["name"],
            author=authors[0].name if authors else "anon",
            authors=authors,
            version=project["version"],
            summary=project.get("description", ""),
            readme=project.get("readme", "README.md"),
            license=project.get("license", "MIT"),
            classifiers=project.get("classifiers", []),
            build=BuildConfig(
                extensions=[
                    Extension(**d) 
                    for d in kajol_config.get("c_exts", [])
                ],
                ignore=kajol_config.get("ignore", []),
                deps=project.get("dependencies", []),
                entry_pts=project.get("scripts", {}),
                compileall=kajol_config.get("compileall", False)
            )
        )
        
        if "vendor" in kajol_config:
            c.build.vendor = VendorConfig(**kajol_config["vendor"])
        
        return c

    def pyproject(self):
        toml = {
            "build-system": {
                "requires": [f"https://github.com/tiash-and-cats/kajol/"
                             f"releases/download/v{kajol.__version__
                             }/kajol-{kajol.__version__}-cp314-none-"
                             f"any.whl"],
                "build-backend": "kajol.do_build"
            },
            "project": {
                "name": self.name,
                "version": self.version,
                "readme": self.readme,
                "license": self.license,
                "dependencies": self.build.deps,
                "authors": list(map(Author.toml, self.authors)),
                "classifiers": self.classifiers,
                "scripts": self.build.entry_pts,
                "description": self.summary,
            },
            "tool": {"kajol": {
                "ignore": self.build.ignore,
                "compileall": self.build.compileall
            }}
        }
        
        if self.build.vendor:
            toml["tool"]["kajol"]["vendor"] = {
                "pth_file": self.build.vendor.pth_file,
                "pkg_dir": self.build.vendor.pkg_dir
            }
        
        if self.build.extensions:
            toml["tool"]["kajol"]["c_exts"] = list(map(
                Extension.toml, self.build.extensions
            ))
        
        return tomlkit.dumps(toml)