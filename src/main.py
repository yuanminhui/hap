import argparse
import sys
import importlib


VERSION = "0.1.0"
MODULE_LIST = ["hpbuilder"]
module_help_map = {}


def create_parser():
    parser = argparse.ArgumentParser(
        prog="palchemy",
        description="Toolkit for Prowse data convertion.",
        usage="%(prog)s <command> [options]",
        exit_on_error=False,
    )
    parser.add_argument(
        "-v", "--version", action="version", version="%(prog)s %(VERSION)s"
    )
    subparsers = parser.add_subparsers(
        title="commands", dest="command", required=True, metavar=""
    )
    for module in MODULE_LIST:
        importlib.import_module("commands." + module).register_command(
            subparsers, module_help_map
        )

    return parser


def main():
    parser = create_parser()
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    try:
        args = parser.parse_args()
        if hasattr(args, "func"):
            args.func(args)
    except (argparse.ArgumentError, SystemExit) as e:
        if len(sys.argv) == 2:
            if sys.argv[1] in MODULE_LIST:
                module_help_map[sys.argv[1]]()
            else:
                parser.print_help(sys.stderr)
        else:
            print(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
