"""CLI entry point: python -m table2rules [input] [output]"""

import argparse
import sys

from ._core import process_tables_to_text


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
        "-o", "--output",
        default="-",
        help="Output file (default: stdout)",
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

    result = process_tables_to_text(html)

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
