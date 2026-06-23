from kajol.build import *

conf = Config(name='kajol',
       author='tiash-and-cats',
       version='1.1.0',
       summary='the kajol dependency manager: a FAST package manager (whoosh!)',
       readme='README.md',
       license='MIT',
       classifiers=[],
       build=BuildConfig(extensions=[],
                         ignore=["env/*", "test/*", "docs/*", ".git/*"],
                         deps=["requests", "packaging"],
                         vendor_dir="kajol/_vendor",
                         entry_pts={"kajol": "kajol.__main__:main"}))
