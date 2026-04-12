#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import List

from table2rules import process_tables_to_text


ROOT = Path(__file__).resolve().parent
TEST_DIR = ROOT / "test tables"
BENCH_DIR = ROOT / "benchmarks"
CURRENT_DIR = BENCH_DIR / "current"
GOLD_DIR = BENCH_DIR / "gold"


@dataclass
class CaseResult:
    name: str
    status: str
    output_lines: int
    gold_lines: int
    diff: str = ""


def discover_cases() -> List[Path]:
    return sorted(TEST_DIR.rglob("*.md"))


def rel_case_path(path: Path) -> Path:
    return path.relative_to(TEST_DIR)


def out_path(base: Path, case_path: Path) -> Path:
    rel = rel_case_path(case_path).with_suffix(".out.txt")
    return base / rel


def non_empty_line_count(text: str) -> int:
    return sum(1 for ln in text.splitlines() if ln.strip())


def run_case(case_path: Path) -> str:
    html = case_path.read_text(encoding="utf-8")
    return process_tables_to_text(html)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def maybe_write(path: Path, content: str, enabled: bool) -> None:
    if not enabled:
        return
    ensure_parent(path)
    path.write_text(content, encoding="utf-8")


def compare_case(case_path: Path, output: str, allow_missing_gold: bool) -> CaseResult:
    case_name = str(rel_case_path(case_path))
    gold_path = out_path(GOLD_DIR, case_path)

    output_lines = non_empty_line_count(output)
    if not gold_path.exists():
        status = "MISSING_GOLD_OK" if allow_missing_gold else "MISSING_GOLD"
        return CaseResult(
            name=case_name,
            status=status,
            output_lines=output_lines,
            gold_lines=0,
        )

    gold = gold_path.read_text(encoding="utf-8")
    gold_lines = non_empty_line_count(gold)
    if output == gold:
        return CaseResult(
            name=case_name,
            status="PASS",
            output_lines=output_lines,
            gold_lines=gold_lines,
        )

    diff_lines = difflib.unified_diff(
        gold.splitlines(keepends=True),
        output.splitlines(keepends=True),
        fromfile=f"gold/{case_name}",
        tofile=f"current/{case_name}",
        n=2,
    )
    return CaseResult(
        name=case_name,
        status="FAIL",
        output_lines=output_lines,
        gold_lines=gold_lines,
        diff="".join(diff_lines),
    )


def print_report(results: List[CaseResult], show_diff: bool) -> None:
    print("\nTable2Rules Benchmark Report")
    print("=" * 28)

    for res in results:
        print(
            f"[{res.status}] {res.name} "
            f"(output={res.output_lines} lines, gold={res.gold_lines} lines)"
        )
        if show_diff and res.diff:
            print(res.diff)

    counts = {}
    for res in results:
        counts[res.status] = counts.get(res.status, 0) + 1

    print("\nSummary")
    print("-" * 7)
    for key in sorted(counts.keys()):
        print(f"{key}: {counts[key]}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run benchmark comparisons for all markdown test tables."
    )
    parser.add_argument(
        "--update-gold",
        action="store_true",
        help="Overwrite gold outputs with current outputs.",
    )
    parser.add_argument(
        "--no-write-current",
        action="store_true",
        help="Do not write current outputs to benchmarks/current.",
    )
    parser.add_argument(
        "--allow-missing-gold",
        action="store_true",
        help="Treat missing gold files as non-failing.",
    )
    parser.add_argument(
        "--show-diff",
        action="store_true",
        help="Show unified diff for failing cases.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = discover_cases()
    if not cases:
        print(f"No .md cases found under: {TEST_DIR}")
        return 1

    results: List[CaseResult] = []
    write_current = not args.no_write_current

    for case in cases:
        output = run_case(case)
        maybe_write(out_path(CURRENT_DIR, case), output, write_current)
        if args.update_gold:
            maybe_write(out_path(GOLD_DIR, case), output, enabled=True)
            results.append(
                CaseResult(
                    name=str(rel_case_path(case)),
                    status="GOLD_UPDATED",
                    output_lines=non_empty_line_count(output),
                    gold_lines=non_empty_line_count(output),
                )
            )
        else:
            results.append(compare_case(case, output, args.allow_missing_gold))

    print_report(results, show_diff=args.show_diff)

    failing_statuses = {"FAIL", "MISSING_GOLD"}
    has_failures = any(r.status in failing_statuses for r in results)
    return 1 if has_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
