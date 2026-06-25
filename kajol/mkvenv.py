import venv
import sysconfig
import shutil
import os
from pathlib import Path
from kajol.install import site_packages as sys_site_packages

class EnvBuilder(venv.EnvBuilder):
    def __init__(self, system_site_packages=False, clear=False, symlinks=False
                 , upgrade=False, with_kajol=True, prompt=None, *, 
                 scm_ignore_files=frozenset()):
        self.with_kajol = with_kajol
        super().__init__(system_site_packages, clear, symlinks, upgrade, 
                         False, prompt, False, scm_ignore_files=
                         scm_ignore_files)
    
    def post_setup(self, context):
        if self.with_kajol:
            # locate site-packages inside the new venv
            env_site_packages = Path(context.lib_path)
            
            try:
                dist_info = next(filter(
                    lambda x: x.name.startswith("kajol-") and \
                    x.name.endswith(".dist-info"),
                    sys_site_packages().iterdir()
                ))
            except StopIteration:
                raise FileNotFoundError("couldn't find a kajol-*.dist-info in site-packages!")

            # copy kajol package into site-packages
            shutil.copytree(sys_site_packages() / "kajol", 
                            env_site_packages / "kajol")
            shutil.copytree(dist_info, env_site_packages / dist_info.name)
            
            # make the kajol launcher
            with open(Path(context.bin_path) / 
                      f"kajol{".bat" if os.name ==  "nt" else ""}", "w") as f:
                if os.name != "nt":
                    print("#!/bin/sh", file=f)
                else:
                    print("@echo off", file=f)
                print(f"python -m kajol {"$" if os.name != "nt" else "%"}*",
                      file=f)
            
            shutil.copy(
                sys_site_packages() / "_kajol_vendor.pth", 
                env_site_packages / "_kajol_vendor.pth"
            )