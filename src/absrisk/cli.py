"""Command line entry point. Subcommands are added as tasks land (see TASKS.md)."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="absrisk")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("version", help="print version")
    args = parser.parse_args(argv)
    if args.cmd == "version":
        from . import __version__

        print(__version__)
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
