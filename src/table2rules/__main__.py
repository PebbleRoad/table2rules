"""CLI entry point: python -m table2rules [input] [output]"""

import argparse
import sys

from . import __version__
from ._core import process_tables_to_text, process_tables_with_stats
from .errors import Table2RulesError
from .exporters import DEFAULT_FORMAT, available_exporters


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="table2rules",
        description="Convert HTML tables to flat, LLM-friendly rules.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Input file (default: stdin)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Output file (default: stdout)",
    )
    parser.add_argument(
        "-f",
        "--format",
        default=DEFAULT_FORMAT,
        choices=available_exporters(),
        help=f"Output exporter (default: {DEFAULT_FORMAT})",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on parse errors or oversized tables instead of degrading.",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    args = parser.parse_args()

    # Read input
    if args.input == "-":
        html = sys.stdin.read()
    else:
        try:
            with open(args.input, "r", encoding="utf-8") as f:
                html = f.read()
        except FileNotFoundError:
            print(f"error: file not found: {args.input}", file=sys.stderr)
            sys.exit(1)
        except IsADirectoryError:
            print(f"error: is a directory: {args.input}", file=sys.stderr)
            sys.exit(1)

    try:
        if args.strict:
            result, _ = process_tables_with_stats(html, format=args.format, strict=True)
        else:
            result = process_tables_to_text(html, format=args.format)
    except Table2RulesError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    # Write output
    if args.output == "-":
        sys.stdout.write(result)
    else:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(result)
        except (PermissionError, IsADirectoryError) as e:
            print(f"error: cannot write to {args.output}: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
