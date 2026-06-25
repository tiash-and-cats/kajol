import argparse
import sys
import os
from kajol.install import install, uninstall, sp_cleanup_empty_dirs
from kajol.do_build import init, build
from kajol.mkvenv import EnvBuilder

def main():
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
    
    args = parser.parse_args()
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

if __name__ == "__main__": 
    sys.exit(main())