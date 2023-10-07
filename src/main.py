import argparse
import sys
import importlib

from . import palchinfo


def create_parser():
    """Create the CLI parser with subcommands and their help messages."""

    module_help_map = {}
    parser = argparse.ArgumentParser(
        prog=palchinfo.name,
        description="Toolkit for Prowse data convertion.",
        usage=f"{palchinfo.name} <command> [options]",
        exit_on_error=False,
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"{palchinfo.name} {palchinfo.version}",
    )
    subparsers = parser.add_subparsers(
        title="commands", dest="command", required=True, metavar=""
    )
    for module in palchinfo.modules:
        importlib.import_module(f".{module}", "src.commands").register_command(
            subparsers, module_help_map
        )

    return parser, module_help_map


def main():
    parser, module_help_map = create_parser()

    # print help when no arguments is given
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    try:
        args = parser.parse_args()
        if hasattr(args, "func"):
            args.func(args)
    except (argparse.ArgumentError, SystemExit) as e:
        if len(sys.argv) == 2:
            if sys.argv[1] in palchinfo.modules:
                module_help_map[sys.argv[1]]()
            else:
                parser.print_help(sys.stderr)
        else:
            print(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
