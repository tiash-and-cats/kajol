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
    extensions: list[Extension] = field(default_factory=list)
    ignore: list[str] = field(default_factory=list)
    
    deps: list[str] = field(default_factory=list)
    vendor: VendorConfig | None = None
    
    entry_pts: dict[str, str] = field(default_factory=dict)

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
        
        return Config(
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
                vendor_dir=kajol_config.get("vendor_dir"),
                entry_pts=project.get("scripts", {})
            )
        )
    
    def pyproject(self):
        toml = {
            "build-system": {
                "requires": ["https://github.com/tiash-and-cats/kajol/"
                             "releases/download/v1.1.1/kajol-1.1.1-cp314-none-"
                             "any.whl"],
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
                "ignore": self.build.ignore
            }}
        }
        
        if self.build.vendor_dir:
            toml["tool"]["kajol"]["vendor_dir"] = self.build.vendor_dir
        
        if self.build.extensions:
            toml["tool"]["kajol"]["c_exts"] = list(map(
                Extension.toml, self.build.extensions
            ))
        
        return tomlkit.dumps(toml)