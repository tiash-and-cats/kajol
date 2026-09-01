from operator import itemgetter
from kajol.pyinstall import pystandalone, ftp, ancient
from kajol.pyinstall.shared import *
from kajol.pyinstall.shared import _installed_python

def install_python(version, *, auto_retry=True):
    try:
        if latest_python(version) in map(itemgetter(0), _installed_python()):
            return print("Python", version, "is already installed.")
    except FileNotFoundError: pass
    
    if Version(version) < Version("3.10"):
        if Version(version) < Version("2.0"):
            print(
                "======= entering archaeology mode: resurrecting Python <2.0"
            )
            return ancient.install_python(version, auto_retry)
        
        print("======= python-build-standalone only has >=3.10, trying ftp")
        return ftp.install_python(version, auto_retry)
    
    try:
        return pystandalone.install_python(version, auto_retry)
    except FileNotFoundError:
        print("======= could not find on python-build-standalone, trying ftp")
        return ftp.install_python(version, auto_retry)