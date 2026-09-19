import sys
from pathlib import Path

# force vendor dir to front of sys.path
sys.path.insert(0, str(Path(__file__).parent / "_vendor"))

import argparse
import os
from kajol.install import install, uninstall, sp_cleanup_empty_dirs
from kajol.do_build import init, build
from kajol.mkvenv import EnvBuilder
from kajol.pyinstall import (install_python, latest_python, uninstall_python, 
                             list_installed_python, list_available_python,
                             exec_python, shell)
def init_venv_cli(sub):
    # modified from stdlib venv cli
    cmd_venv = sub.add_parser("venv", description='Creates virtual Python '
                                                  'environments in one or '
                                                  'more target '
                                                  'directories.',
                                      epilog='Once an environment has been '
                                             'created, you may wish to '
                                             'activate it, e.g. by '
                                             'sourcing an activate script '
                                             'in its bin directory.')
    cmd_venv.add_argument('dirs', metavar='ENV_DIR', nargs='+',
                          help='A directory to create the environment in.')
    cmd_venv.add_argument('--system-site-packages', default=False,
                          action='store_true', dest='system_site',
                          help='Give the virtual environment access to the '
                               'system site-packages dir.')
    if os.name == 'nt':
        use_symlinks = False
    else:
        use_symlinks = True
    group1 = cmd_venv.add_mutually_exclusive_group()
    group1.add_argument('--symlinks', default=use_symlinks,
                        action='store_true', dest='symlinks',
                        help='try to use symlinks rather than copies, '
                             'when symlinks are not the default for '
                             'the platform.')
    group1.add_argument('--copies', default=not use_symlinks,
                       action='store_false', dest='symlinks',
                       help='try to use copies rather than symlinks, '
                            'even when symlinks are the default for '
                            'the platform.')
    group2 = cmd_venv.add_mutually_exclusive_group()
    group2.add_argument('--clear', default=False, action='store_true',
                        dest='clear', help='delete the contents of the '
                                           'environment directory if it '
                                           'already exists, before '
                                           'environment creation.')
    group2.add_argument('--upgrade', default=False, action='store_true',
                        dest='upgrade', help='upgrade the environment '
                                             'directory to use this version '
                                             'of Python, assuming Python '
                                             'has been upgraded in-place.')
    cmd_venv.add_argument('--without-kajol', dest='with_kajol',
                        default=True, action='store_false',
                        help='skips installing or upgrading kajol in the '
                             'virtual environment (kajol is bootstrapped '
                             'by default)')
    cmd_venv.add_argument('--prompt',
                          help='provides an alternative prompt prefix for '
                               'this environment.')
    cmd_venv.add_argument('--without-scm-ignore-files', dest='scm_ignore_files',
                          action='store_const', const=frozenset(),
                          default=frozenset(['git']),
                          help='skips adding SCM ignore files to the environment '
                               'directory (Git is supported by default).')

def init_pyinstall_cli(main_sub):
    parser = main_sub.add_parser("python", aliases=["py"],
                                 help="manage Python installs")
    
    sub = parser.add_subparsers(dest="pycommand", required=True)

    cmd_pyinstall = sub.add_parser("install", aliases=["i"], 
                                   help="install a version of Python")
    
    cmd_pyinstall.add_argument(
        "version", nargs='?', default="latest", help="the version to install"
    )
    cmd_pyinstall.add_argument(
        "--no-auto-retry", 
        help="don't automatically retry a previous micro version if an "
             "installer is not found",
        action='store_true'
    )

    cmd_list = sub.add_parser("list",
                              help="list Python installs managed by kajol")

    cmd_uninstall = sub.add_parser("uninstall", aliases=["u"], 
                                   help="uninstall a Python version")
    cmd_uninstall.add_argument("versions", nargs="*", 
                               help="the Python version(s) to uninstall")

    cmd_available = sub.add_parser("available",
                                   help="list available Python versions")
    cmd_available.add_argument(
        "-v", "--verbose", help="change verbosity level",
        action="store_true"
    )
    
    cmd_exec = sub.add_parser("exec",
                              help="execute a kajol-managed install of "
                                   "Python")
    cmd_exec.add_argument('-v', "--version",
                          help="the version of Python to use")

    cmd_sh = sub.add_parser("shell", aliases=["sh"],
                            help="start a shell with a specified default "
                                 "version of Python (defaults to the latest "
                                 "installed version)")
    cmd_sh.add_argument('-v', "--version",
                        help="the version of Python to use")

def pyinstall_cli(args):
    match args.pycommand:
        case "install" | "i":
            install_python(
                latest_python(args.version), 
                auto_retry=not args.no_auto_retry
            )
        case "list":
            list_installed_python()
        case "uninstall" | "u":
            for v in args.versions:
                uninstall_python(v)
        case "available":
            list_available_python(verbose=args.verbose, cmdline=True)
        case "exec":
            exec_args = args.args
            exec_python(args.version, exec_args)
        case "shell" | "sh":
            shell(args.version)

def main():
    forwarded_args = []
    original_argv = sys.argv[:]
    
    for idx in range(len(sys.argv) - 1):
        if sys.argv[idx].startswith("py") and sys.argv[idx + 1] == "exec":
            exec_idx = idx + 1
            # Look for wrapper flag values directly after 'exec'
            stop_idx = exec_idx + 1
            if stop_idx < len(sys.argv) and sys.argv[stop_idx] in ('-v', '--version'):
                stop_idx += 2 # Skip over the flag and its value string
                
            # Isolate everything after wrapper definitions to forward cleanly
            forwarded_args = sys.argv[stop_idx:]
            sys.argv = sys.argv[:stop_idx]
            break

    parser = argparse.ArgumentParser(
        description="kajol dependency manager: a FAST package manager (whoosh!)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    cmd_install = sub.add_parser("install", aliases=["i"], 
                                 help="install a package")
    cmd_install.add_argument("pkg", nargs="*", help="the package specifier(s) "
                             "to install. if not given, kajol.lock.pkl is read"
                             "and packages from that file are installed. the "
                             "--no-deps option has no effect in this matter.")
    cmd_install.add_argument("-u", "--user", action="store_true", help="if present,"
                             "per-user install; otherwise system (or venv) wide")
    cmd_install.add_argument("--no-deps", action="store_true", help="if present,"
                             "dependencies will not be installed")

    cmd_uninstall = sub.add_parser("uninstall", aliases=["u"], 
                                   help="uninstall a package")
    cmd_uninstall.add_argument("pkg", nargs="*", help="the package name(s) to uninstall")
    cmd_uninstall.add_argument("-u", "--user", action="store_true", help= \
                               "pass this if the package was originally a per-user"
                               "install")
    cmd_uninstall.add_argument("-y", "--yes", action="store_true", help="say "
                               "yes to any prompts kajol might ask")

    cmd_build = sub.add_parser("build", help="build a package to a .whl")
    cmd_genconf = sub.add_parser("init", help="scaffold a package for build")

    init_venv_cli(sub)
    init_pyinstall_cli(sub)

    args = parser.parse_args()
    
    if args.command.startswith("py") and args.pycommand == "exec":
        args.args = forwarded_args

    match args.command:
        case "install" | "i":
            install(args.pkg, user=args.user, deps=not args.no_deps)
        case "uninstall" | "u":
            for pkg in args.pkg:
                uninstall(pkg, user=args.user, yes=args.yes)
            sp_cleanup_empty_dirs(user=args.user)
        case "build":
            build()
        case "init":
            init()
        case "venv":
            options = args
            builder = EnvBuilder(system_site_packages=options.system_site,
                                 clear=options.clear,
                                 symlinks=options.symlinks,
                                 upgrade=options.upgrade,
                                 with_kajol=options.with_kajol,
                                 prompt=options.prompt,
                                 scm_ignore_files=options.scm_ignore_files)
            for d in options.dirs:
                builder.create(d)
        case "python" | "py":
            pyinstall_cli(args)

if __name__ == "__main__": 
    sys.exit(main())