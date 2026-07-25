from kajol.build import *

keywdarg = Extension(
    files=["test/keywdarg.c"],
    output="test/keywdarg"
)

conf = Config(name='test',
       author='Eric Idle',
       version='0.0.0',
       summary='',
       readme='README.md',
       license='MIT',
       classifiers=[],
       build=BuildConfig(extensions=[keywdarg],
                         ignore=[],
                         vendor=VendorConfig(
                            pkg_dir="test/vendor",
                            pth_file="test/vendor.pth"
                         )))

