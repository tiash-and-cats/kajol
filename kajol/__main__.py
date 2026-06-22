import argparse
import sys
from kajol.install import install, uninstall, sp_cleanup_empty_dirs
from kajol.do_build import init, build

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

if __name__ == "__main__": 
    sys.exit(main())