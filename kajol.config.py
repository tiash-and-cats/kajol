import kajol
from kajol.build import *

conf = Config(name='kajol',
       author='tiash-and-cats',
       version=kajol.__version__,
       summary='the kajol dependency manager: a FAST package manager (whoosh!)',
       readme='README.md',
       license='MIT',
       classifiers=[
          "Programming Language :: Python :: 3",
          "License :: OSI Approved :: MIT License"
       ],
       build=BuildConfig(extensions=[],
                         ignore=[
                            "env/*", "ktest/*", "docs/*", ".git/*",
                            "pyproject.toml", "*/__pycache__/*",
                            "__pycache__/*", ".gitignore", "build/*",
                            "manywhl/*", "benchmark.md", "ienv.bat",
                            "kajol_config.py"
                         ],
                         deps=[
                            "tomlkit", "requests", "packaging", "llvmlite",
                            "shellingham",
                            'zstandard; python_version < "3.14"',
                         ],
                         vendor=VendorConfig(
                            pth_file="_kajol_vendor.pth",
                            pkg_dir="kajol/_vendor",
                         ),
                         entry_pts={"kajol": "kajol.__main__:main"},
                         compileall=True))
