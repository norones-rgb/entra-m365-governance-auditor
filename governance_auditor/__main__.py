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
    reviews = sub.add_parser("review-export", help="Read-only Graph access-review status/decision-count export")
    reviews.add_argument("--tenant-id", required=True, help="Entra tenant GUID")
    reviews.add_argument("--client-id", required=True, help="Public-client app registration GUID")
    reviews.add_argument("--definition-id", action="append", required=True, help="Review definition GUID (repeatable)")
    reviews.add_argument("--output", type=Path, required=True, help="Fresh local output directory, ideally under reports/")
    reviews.add_argument("--as-of", help="UTC evaluation ISO timestamp (defaults to now)")
    recon = sub.add_parser("reconcile-sharepoint", help="Offline Entra/SharePoint principal reconciliation with explicit source coverage")
    recon.add_argument("--graph", type=Path, required=True, help="Selected-group Graph export directory")
    recon.add_argument("--sharepoint", type=Path, required=True, help="Selected-site PnP export directory")
    recon.add_argument("--output", type=Path, required=True, help="Fresh local report directory")
    drift = sub.add_parser("compare-snapshots", help="Offline selected-scope Entra/SharePoint drift report")
    drift.add_argument("--before-graph", type=Path, required=True, help="Earlier selected-group Graph export")
    drift.add_argument("--after-graph", type=Path, required=True, help="Later selected-group Graph export")
    drift.add_argument("--before-sharepoint", type=Path, help="Optional earlier selected-site PnP export")
    drift.add_argument("--after-sharepoint", type=Path, help="Optional later selected-site PnP export")
    drift.add_argument("--output", type=Path, required=True, help="New local comparison report directory")
    args = parser.parse_args(argv)
    if args.command == "compare-snapshots":
        from .snapshot_diff import ComparisonError, compare_snapshots
        try:
            summary = compare_snapshots(args.before_graph, args.after_graph, args.output,
                                        args.before_sharepoint, args.after_sharepoint)
        except (OSError, ValueError, csv.Error, ComparisonError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"Observed changes: {summary['changes']} | Non-comparable scopes: {summary['non_comparable_scopes']}")
        print("Offline direct observations only; not effective access or proof of revocation.")
        print(f"Local report: {args.output}")
        return 0
    if args.command == "reconcile-sharepoint":
        from .reconcile import ReconcileError, reconcile
        try:
            summary = reconcile(args.graph, args.sharepoint, args.output)
        except (OSError, ValueError, csv.Error, ReconcileError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"SharePoint observations: {summary['observation_count']} | Resolved: {summary['resolution_counts']['matched']} | "
              f"Disabled-user review indicators: {summary['disabled_account_review_indicators']}")
        print("Partial identity correlation only; not effective permissions or approval evidence.")
        return 0
    if args.command == "review-export":
        from .graph_export import GraphClient, GraphExportError, acquire_delegated_token, valid_guid
        from .review_export import REVIEW_SCOPES, export_reviews, _parse_date_time
        try:
            tenant = valid_guid(args.tenant_id, "--tenant-id")
            client_id = valid_guid(args.client_id, "--client-id")
            definitions = [valid_guid(i, "--definition-id") for i in args.definition_id]
            as_of = _parse_date_time(args.as_of, "--as-of") if args.as_of else None
            if args.output.exists():
                raise GraphExportError("Output path already exists; choose a new directory")
            token = acquire_delegated_token(tenant, client_id, REVIEW_SCOPES)
            summary = export_reviews(GraphClient(token), definitions, args.output, as_of)
        except (GraphExportError, OSError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"Exported {summary['instance_count']} review instances from {len(definitions)} selected definitions to {args.output}")
        print("This read-only report contains decision counts, not individual decision identities or approval evidence.")
        return 0
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
