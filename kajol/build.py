from dataclasses import dataclass, field

@dataclass
class Extension:
    files: list[str]
    output: str | None = None

@dataclass
class BuildConfig:
    extensions: list[Extension] = field(default_factory=list)
    ignore: list[str] = field(default_factory=list)
    
    deps: list[str] = field(default_factory=list)
    vendor_dir: str = None
    
    entry_pts: dict[str, str] = field(default_factory=dict)

@dataclass
class Config:
    name: str
    author: str
    version: str
    summary: str = ""
    readme: str = "README.md"
    license: str = "MIT"
    classifiers: list[str] = field(default_factory=list)
    build: BuildConfig = field(default_factory=BuildConfig)