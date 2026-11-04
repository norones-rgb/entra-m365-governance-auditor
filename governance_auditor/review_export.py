"""Selected Microsoft Graph access-review status and decision-count reporting.

Read only. Never exports decision subjects, user IDs or reviewer identities.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from .graph_export import GraphClient, GraphExportError, valid_guid

REVIEW_SCOPES = ["AccessReview.Read.All"]
DONE = {"completed", "autoreviewed"}
MAX_DEFINITIONS = 20
MAX_INSTANCES = 200
MAX_DECISIONS = 10000
FIELDS = ("definition_id", "definition_name", "instance_id", "status", "started_utc", "ends_utc",
          "overdue", "decision_total", "approve", "deny", "not_reviewed", "other")


def _parse_date_time(raw: str, label: str) -> dt.datetime | None:
    if not raw:
        return None
    if not isinstance(raw, str):
        raise GraphExportError(f"{label} must be an ISO datetime")
    try:
        val = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise GraphExportError(f"{label} must be an ISO datetime") from None
    if val.tzinfo is None:
        raise GraphExportError(f"{label} must include a timezone")
    return val.astimezone(dt.timezone.utc)


def _normalize_decision(raw: object) -> str:
    value = str(raw or "").strip().casefold()
    if value in ("approve", "approved"):
        return "approve"
    if value in ("deny", "denied"):
        return "deny"
    if value in ("notreviewed", "not_reviewed"):
        return "not_reviewed"
    return "other"


def _csv_safe(value: object) -> str:
    value = str(value if value is not None else "")
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows([{key: _csv_safe(row.get(key, "")) for key in fields} for row in rows])


def _render_html(rows: list[dict], as_of: dt.datetime) -> str:
    overdue = sum(row["overdue"] == "true" for row in rows)
    undecided = sum(row["not_reviewed"] for row in rows)
    columns = ["Campaign", "Instance", "Status", "Due (UTC)", "Overdue?", "Decisions", "Not reviewed"]
    def cell(value: object) -> str:
        return html.escape(str(value), quote=True)
    table_rows = []
    for r in rows:
        cols = [r["definition_name"], r["instance_id"], r["status"], r["ends_utc"],
                r["overdue"], r["decision_total"], r["not_reviewed"]]
        table_rows.append("<tr>" + "".join(f"<td>{cell(x)}</td>" for x in cols) + "</tr>")
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            "content='width=device-width, initial-scale=1'><title>Access Review Snapshot</title>"
            "<style>body{font:15px system-ui,sans-serif;color:#20252c;max-width:1100px;margin:3rem auto;padding:0 1rem}"
            "table{border-collapse:collapse;width:100%;margin-top:1.5rem}td,th{padding:.65rem;text-align:left;border-bottom:1px solid #ddd}"
            "th{background:#f4f3f0}.cards{display:flex;gap:1rem;flex-wrap:wrap}.card{padding:1rem;border:1px solid #ddd;border-radius:8px}"
            "small{color:#58616e}</style></head><body><h1>Access Review Snapshot</h1>"
            f"<p><small>UTC evaluation: {cell(as_of.isoformat())}. Read-only; selected definitions only; "
            "these are status indicators, not compliance determinations.</small></p>"
            f"<div class='cards'><div class='card'><strong>{len(rows)}</strong> instances</div>"
            f"<div class='card'><strong>{overdue}</strong> overdue indicators</div>"
            f"<div class='card'><strong>{undecided}</strong> not-reviewed decisions</div></div>"
            "<table><thead><tr>" + "".join(f"<th>{cell(col)}</th>" for col in columns) + "</tr></thead><tbody>"
            + "".join(table_rows) + "</tbody></table>"
            "<p><small>No decision subjects or reviewer identities were exported. A missing due date is unknown, not overdue. "
            "Verify campaign scope, lifecycle stage and permissions before interpreting results.</small></p></body></html>\n")


def export_reviews(client: GraphClient, definition_ids: list[str], output: Path,
                   as_of: dt.datetime | None = None) -> dict:
    ids = [valid_guid(i, "review definition ID") for i in definition_ids]
    if not ids or len(ids) > MAX_DEFINITIONS or len(set(ids)) != len(ids):
        raise GraphExportError("Select 1 to 20 unique review definition IDs")
    output = Path(output).resolve()
    if output.exists():
        raise GraphExportError("Output path already exists; choose a fresh directory")
    now = as_of or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise GraphExportError("--as-of must have a timezone")
    now = now.astimezone(dt.timezone.utc)
    rows: list[dict] = []
    for did in ids:
        definition = client.get(f"/identityGovernance/accessReviews/definitions/{quote(did)}")
        if definition.get("id") != did:
            raise GraphExportError("Graph returned a definition ID different from the selected ID")
        label = definition.get("displayName") or did
        instances = client.pages(f"/identityGovernance/accessReviews/definitions/{quote(did)}/instances")
        if len(instances) > MAX_INSTANCES:
            raise GraphExportError("Too many review instances; narrow your export")
        seen = set()
        for inst in instances:
            iid = valid_guid(inst.get("id"), "review instance ID")
            if iid in seen:
                raise GraphExportError("Duplicate instance ID returned")
            seen.add(iid)
            status = inst.get("status", "")
            if not isinstance(status, str):
                raise GraphExportError("Invalid review status")
            started = _parse_date_time(inst.get("startDateTime"), "review startDateTime")
            ends = _parse_date_time(inst.get("endDateTime"), "review endDateTime")
            decisions = client.pages(f"/identityGovernance/accessReviews/definitions/{quote(did)}/instances/{quote(iid)}/decisions")
            if len(decisions) > MAX_DECISIONS:
                raise GraphExportError("Too many decisions in a single instance")
            counts = Counter(_normalize_decision(d.get("decision")) for d in decisions)
            overdue = bool(ends and ends < now and status.casefold() not in DONE)
            rows.append({"definition_id": did, "definition_name": str(label), "instance_id": iid,
                         "status": status or "unknown", "started_utc": started.isoformat() if started else "",
                         "ends_utc": ends.isoformat() if ends else "", "overdue": str(overdue).lower(),
                         "decision_total": len(decisions), "approve": counts["approve"],
                         "deny": counts["deny"], "not_reviewed": counts["not_reviewed"],
                         "other": counts["other"]})
    manifest = {
        "schema": "graph-reviews-v0.3", "source": "Microsoft Graph v1.0", "collected_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "as_of_utc": now.isoformat(), "selected_definition_ids": ids,
        "instance_count": len(rows), "overdue_indicators": sum(x["overdue"] == "true" for x in rows),
        "review_status_coverage": "Only selected definitions and returned instances; per-instance decision counts, not participant-level records.",
        "limitations": ["No assessment of reviewer decisions or quality", "No automatic revocation or remediation",
                        "No participant identities included", "Missing instances or due dates cannot establish compliance", "Read access is subject to Entra roles and license eligibility"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".review-staging-", dir=output.parent))
    try:
        _write_csv(staging / "review_instances.csv", FIELDS, rows)
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (staging / "dashboard.html").write_text(_render_html(rows, now), encoding="utf-8")
        staging.rename(output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return manifest
