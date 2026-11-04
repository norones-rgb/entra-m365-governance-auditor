"""CLI: python -m governance_auditor scan --input ... --output ..."""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import sys
from pathlib import Path
from .engine import analyze, parse_date
from .reporting import write_reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline, read-only Entra/M365 governance snapshot auditor")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="Evaluate normalized CSV snapshots")
    scan.add_argument("--input", type=Path, required=True, help="Directory of 9 normalized CSV inputs")
    scan.add_argument("--output", type=Path, required=True, help="New or existing directory for generated reports")
    scan.add_argument("--as-of", default=dt.date.today().isoformat(), help="Snapshot evaluation date YYYY-MM-DD")
    args = parser.parse_args(argv)
    try:
        as_of = parse_date(args.as_of, "--as-of")
        if args.input.resolve() == args.output.resolve():
            raise ValueError("Input and output directories must differ")
        audit = analyze(args.input, as_of)
        reports = write_reports(audit, args.output)
    except (OSError, ValueError, csv.Error) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(f"As of: {audit.as_of} | Open: {audit.counts['open']} | High: {audit.counts['high']} | "
          f"Excepted: {audit.counts['excepted']} | Evidence pairs: {audit.counts['correlated_evidence']}")
    for key, path in reports.items():
        print(f"{key}: {path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
