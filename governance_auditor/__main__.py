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
    graph = sub.add_parser("graph-export", help="Read-only Graph export of selected direct group members")
    graph.add_argument("--tenant-id", required=True, help="Entra tenant GUID")
    graph.add_argument("--client-id", required=True, help="Public client application GUID")
    graph.add_argument("--group-id", action="append", required=True, help="Group GUID (repeatable)")
    graph.add_argument("--privileged-group-id", action="append", default=[], help="Explicit privileged group GUID (repeatable)")
    graph.add_argument("--output", type=Path, required=True, help="New local export directory, ideally under reports/")
    args = parser.parse_args(argv)
    if args.command == "graph-export":
        from .graph_export import GraphClient, GraphExportError, acquire_delegated_token, export_snapshot, valid_guid
        try:
            tenant = valid_guid(args.tenant_id, "--tenant-id")
            client_id = valid_guid(args.client_id, "--client-id")
            groups = [valid_guid(g, "--group-id") for g in args.group_id]
            privileged = {valid_guid(g, "--privileged-group-id") for g in args.privileged_group_id}
            if not privileged.issubset(set(groups)):
                raise GraphExportError("Privileged group must be selected with --group-id")
            if args.output.exists():
                raise GraphExportError("Output path already exists; choose a new directory")
            token = acquire_delegated_token(tenant, client_id)
            summary = export_snapshot(GraphClient(token), groups, privileged, args.output)
        except (GraphExportError, OSError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"Exported {summary['records']['groups']} selected groups and {summary['records']['direct_user_memberships']} direct user memberships to {args.output}")
        print("Partial inventory only: original grant dates, approval evidence, nested membership and site permissions are not included.")
        return 0
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