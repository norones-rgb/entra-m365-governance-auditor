"""Offline reviewer attestations and evidence packages for v0.5 drift reports.

Human-entered decisions are recorded as *claims*, not independent approval or
access-remediation proofs. No network connections or live changes are made.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import html
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from .snapshot_diff import CHANGE_FIELDS, COVER_FIELDS, _safe_csv


class ReviewError(ValueError):
    """An unsafe, incomplete or incompatible review package input."""


PLAN_FIELDS = (
    "change_id", "disposition", "reviewer", "reviewed_at_utc", "rationale",
    "action_owner", "action_due_utc", "action_status", "closure_evidence",
    "exception_approved_by", "exception_expires_utc",
)
REPORT_FIELDS = ("change_id",) + CHANGE_FIELDS + PLAN_FIELDS[1:] + ("review_flag",)
ACTION_FIELDS = (
    "change_id", "system", "category", "resource", "principal", "disposition",
    "action_owner", "action_due_utc", "action_status", "closure_evidence", "review_flag",
)
DISPOSITIONS = {"pending", "acknowledged", "investigate", "remediate", "exception"}
ACTIONS = {"open", "in_progress", "closed"}
MAX_BYTES = 12_000_000
MAX_ROWS = 100_000
SOURCE_FILES = ("changes.csv", "coverage.csv", "manifest.json")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 2_000_000:
        raise ReviewError("Missing or unsafe JSON input")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeError, ValueError):
        raise ReviewError("Malformed JSON input") from None
    if not isinstance(data, dict):
        raise ReviewError("Expected a JSON object")
    return data


def _load_csv(path: Path, expected: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_BYTES:
        raise ReviewError(f"Missing or unsafe CSV: {path.name}")
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != list(expected):
                raise ReviewError(f"Unexpected columns in {path.name}")
            rows = []
            for row in reader:
                if len(rows) >= MAX_ROWS or None in row or any(v is None for v in row.values()):
                    raise ReviewError(f"Malformed/oversized CSV: {path.name}")
                rows.append(row)
            return rows
    except (UnicodeError, csv.Error):
        raise ReviewError(f"Unreadable CSV: {path.name}") from None


def _change_id(row: dict[str, str]) -> str:
    canonical = json.dumps({k: row[k] for k in CHANGE_FIELDS}, sort_keys=True,
                           ensure_ascii=False, separators=(",", ":"))
    return "CHG-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16].upper()


def _load_comparison(folder: Path) -> tuple[list[dict], list[dict], dict, dict[str, str]]:
    manifest = _load_json(folder / "manifest.json")
    if manifest.get("schema") != "selected-access-change-v0.5" or manifest.get("no_network") is not True:
        raise ReviewError("Expected a v0.5 offline comparison manifest")
    changes = _load_csv(folder / "changes.csv", CHANGE_FIELDS)
    coverage = _load_csv(folder / "coverage.csv", COVER_FIELDS)
    if len(changes) != manifest.get("changes"):
        raise ReviewError("Comparison manifest change count does not match changes.csv")
    if sum(x["comparable"] == "no" for x in coverage) != manifest.get("non_comparable_scopes"):
        raise ReviewError("Comparison manifest scope coverage count mismatch")
    ids = [_change_id(row) for row in changes]
    if len(set(ids)) != len(ids):
        raise ReviewError("Duplicate change identity in comparison export")
    return changes, coverage, manifest, {name: _sha(folder/name) for name in SOURCE_FILES}


def _separate_output(output: Path, inputs: list[Path]) -> None:
    target = output.resolve()
    if output.exists() or output.is_symlink():
        raise ReviewError("Output must be a fresh directory")
    for input_path in inputs:
        parent = input_path.resolve()
        if target == parent or target.is_relative_to(parent) or parent.is_relative_to(target):
            raise ReviewError("Output must be outside all input directories")


def _atomic_write(output: Path, inputs: list[Path], create) -> None:
    _separate_output(output, inputs)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".review-staging-", dir=output.parent))
    try:
        create(stage)
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _safe_csv(row.get(field, "")) for field in fields})


def initialize_review(comparison: Path, output: Path) -> dict:
    """Create an anchored, editable review sheet for a selected-scope comparison."""
    comparison, output = Path(comparison).resolve(), Path(output)
    changes, _, _, hashes = _load_comparison(comparison)
    rows = [{**{k:"" for k in PLAN_FIELDS}, "change_id":_change_id(change), "disposition":"pending"}
            for change in changes]
    source = {"schema":"offline-review-plan-v0.6", "source_schema":"selected-access-change-v0.5",
              "source_sha256":hashes, "changes":len(changes),
              "limitations":["Editing a CSV is not an authenticated approval", "No access changes occur"]}
    def write(stage):
        _write_csv(stage/"reviews.csv", PLAN_FIELDS, rows)
        (stage/"source.json").write_text(json.dumps(source, indent=2)+"\n", encoding="utf-8")
    _atomic_write(output, [comparison], write)
    return {"changes":len(changes),"review_plan":str(output)}


def _utc(value: str, field: str) -> dt.datetime:
    try:
        if not value or not (value.endswith("Z") or "+" in value[10:] or "-" in value[10:]):
            raise ValueError
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError
        return result.astimezone(dt.timezone.utc)
    except (ValueError, TypeError, AttributeError):
        raise ReviewError(f"Invalid timezone-aware {field}") from None


def _validate_review(row: dict[str,str], as_of: dt.datetime) -> str:
    disp = row["disposition"].strip().lower()
    if disp not in DISPOSITIONS or row["disposition"] != disp:
        raise ReviewError(f"Invalid review disposition for {row['change_id']}")
    other = {k:v.strip() for k,v in row.items() if k not in ("change_id", "disposition")}
    if disp == "pending":
        if any(other.values()):
            raise ReviewError("Pending reviews cannot contain disposition details")
        return "awaiting_review"
    if not all(other[k] for k in ("reviewer", "reviewed_at_utc", "rationale")):
        raise ReviewError("Completed reviews require reviewer, reviewed_at_utc, and rationale")
    reviewed = _utc(other["reviewed_at_utc"], "reviewed_at_utc")
    if reviewed > as_of:
        raise ReviewError("Review time cannot be in the future relative to --as-of")
    if len(other["rationale"]) > 4000 or len(other["reviewer"]) > 240:
        raise ReviewError("Reviewer or rationale exceeds size limit")
    action_keys = ("action_owner", "action_due_utc", "action_status", "closure_evidence")
    exception_keys = ("exception_approved_by", "exception_expires_utc")
    if disp in ("investigate", "remediate"):
        if not (other["action_owner"] and other["action_due_utc"] and other["action_status"] in ACTIONS):
            raise ReviewError("Action owner, UTC due date and status required for tracked actions")
        due = _utc(other["action_due_utc"], "action_due_utc")
        if due < reviewed:
            raise ReviewError("Action due date cannot precede review")
        if other["action_status"] == "closed" and not other["closure_evidence"]:
            raise ReviewError("Closed actions require a closure evidence reference")
        if other["action_status"] != "closed" and other["closure_evidence"]:
            raise ReviewError("Closure evidence requires a closed action")
        if any(other[k] for k in exception_keys):
            raise ReviewError("Action review must not carry exception approval fields")
        return ("action_closed_self_reported" if other["action_status"] == "closed"
                else "action_overdue" if due < as_of else "action_open")
    if any(other[k] for k in action_keys):
        raise ReviewError("Non-action review must not carry remediation action fields")
    if disp == "exception":
        if not all(other[k] for k in exception_keys):
            raise ReviewError("Exception requires named approver and expiration")
        expires = _utc(other["exception_expires_utc"], "exception_expires_utc")
        if expires < reviewed:
            raise ReviewError("Exception expiration cannot precede review")
        if other["exception_approved_by"].casefold() == other["reviewer"].casefold():
            raise ReviewError("Exception approver must be different from reviewer")
        return "exception_expired" if expires < as_of else "exception_self_reported"
    if any(other[k] for k in exception_keys):
        raise ReviewError("Non-exception disposition must not carry exception fields")
    return "reviewed_self_reported"


def _dashboard(rows: list[dict], coverage: list[dict], as_of: str) -> str:
    escape = lambda v: html.escape(str(v), quote=True)
    counts = Counter(r["review_flag"] for r in rows)
    columns = ("change_id", "system", "category", "change", "resource", "principal", "disposition",
               "reviewer", "action_owner", "action_due_utc", "action_status", "review_flag", "rationale")
    def tbl(data, fields):
        return ("<div class='scroll'><table><thead><tr>"+"".join(f"<th>{escape(k.replace('_',' ').title())}</th>" for k in fields)+"</tr></thead><tbody>"
                +"".join("<tr>"+"".join(f"<td>{escape(r.get(k,''))}</td>" for k in fields)+"</tr>" for r in data)+"</tbody></table></div>")
    stats = [("Changes",len(rows)), ("Awaiting review",counts["awaiting_review"]),
             ("Actions open/overdue",counts["action_open"]+counts["action_overdue"]),
             ("Exceptions expired",counts["exception_expired"])]
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Governance Review Package</title><style>body{font:15px/1.55 system-ui,sans-serif;color:#26303b;max-width:1320px;margin:40px auto;padding:0 20px}"
            "h1,h2{letter-spacing:-.03em}.muted{color:#647284}.stats{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}.stat{border:1px solid #d9e0e6;border-radius:10px;padding:18px;min-width:155px}"
            ".stat b{font-size:26px}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse}td,th{padding:11px;text-align:left;border-bottom:1px solid #e1e5e9;min-width:85px;overflow-wrap:anywhere}"
            "th{background:#f3f6f8;font-size:12px;text-transform:uppercase}td{font-size:13px}</style></head><body>"
            "<h1>Governance Review &amp; Evidence</h1><p class='muted'>Offline review package · As of "+escape(as_of)+"</p>"
            "<p>Recorded analyst dispositions are self-reported and must be independently validated. They do not prove access approval, control effectiveness, or remediation.</p>"
            +"<div class='stats'>"+"".join(f"<div class='stat'><b>{v}</b><div class='muted'>{escape(k)}</div></div>" for k,v in stats)+"</div>"
            +"<h2>Reviewed changes</h2>"+tbl(rows,columns)+"<h2>Source coverage</h2>"
            +tbl(coverage,COVER_FIELDS)+"<p class='muted'>Not a tenant-wide assessment. Changes outside comparable selected scopes are omitted. No direct access changes.</p></body></html>\n")


def export_review_package(comparison: Path, plan_dir: Path, output: Path,
                          as_of: dt.datetime) -> dict:
    """Validate anchored review claims and generate a local audit evidence package."""
    comparison, plan_dir, output = Path(comparison).resolve(), Path(plan_dir).resolve(), Path(output)
    if as_of.tzinfo is None:
        raise ReviewError("--as-of must include a UTC offset")
    as_of = as_of.astimezone(dt.timezone.utc)
    if comparison == plan_dir:
        raise ReviewError("Comparison and review plan must be separate")
    changes, coverage, _, hashes = _load_comparison(comparison)
    source = _load_json(plan_dir/"source.json")
    if source.get("schema") != "offline-review-plan-v0.6" or source.get("source_sha256") != hashes or source.get("changes") != len(changes):
        raise ReviewError("Review plan is stale or its source comparison was modified")
    reviews = _load_csv(plan_dir/"reviews.csv", PLAN_FIELDS)
    expected = {_change_id(x):x for x in changes}
    got = {}
    for row in reviews:
        change_id = row["change_id"]
        if change_id not in expected or change_id in got:
            raise ReviewError("Unknown or duplicate change_id in review plan")
        got[change_id] = row
    if set(got) != set(expected):
        raise ReviewError("Review plan is missing change IDs")
    results, actions = [], []
    for change in changes:
        cid = _change_id(change)
        decision = got[cid]
        flag = _validate_review(decision, as_of)
        record = {"change_id":cid, **change, **{key: decision[key] for key in PLAN_FIELDS[1:]}, "review_flag":flag}
        results.append(record)
        if decision["disposition"] in ("investigate", "remediate"):
            actions.append({key: record.get(key, "") for key in ACTION_FIELDS})
    counts = Counter(r["review_flag"] for r in results)
    out = {"schema":"offline-review-evidence-v0.6", "mode":"offline", "no_network":True,
           "as_of_utc":as_of.isoformat(), "changes":len(results), "tracked_actions":len(actions),
           "review_flags":dict(counts), "coverage_warnings":sum(r["comparable"]!="yes" for r in coverage),
           "source_comparison_sha256":hashes,
           "plan_sha256":{"source.json":_sha(plan_dir/"source.json"),"reviews.csv":_sha(plan_dir/"reviews.csv")},
           "limitations":["Review and exception claims are self-reported, not verified electronic signatures",
                          "No external approval or remediation corroboration", "Only previously compared selected-scope observations",
                          "No permission changes, API calls, or effective-access determination"]}
    def write(stage):
        _write_csv(stage/"reviewed_changes.csv",REPORT_FIELDS,results)
        _write_csv(stage/"remediation_actions.csv",ACTION_FIELDS,actions)
        _write_csv(stage/"coverage.csv",COVER_FIELDS,coverage)
        (stage/"dashboard.html").write_text(_dashboard(results,coverage,as_of.isoformat()),encoding="utf-8")
        out["output_sha256"]={p.name:_sha(p) for p in sorted(stage.iterdir()) if p.is_file()}
        (stage/"package_manifest.json").write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    _atomic_write(output,[comparison,plan_dir],write)
    return out