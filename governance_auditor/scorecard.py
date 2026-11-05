"""Offline review-process scorecard for v0.6 evidence packages.

Metrics describe the *documentation workflow* and selected export coverage.
They are not a measure of tenant security, effective permissions, audit
attestation, or regulatory compliance. Zero-denominator metrics are N/A.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import hmac
import html
import json
from collections import Counter
from pathlib import Path

from .governance_review import (
    ACTION_FIELDS, COVER_FIELDS, REPORT_FIELDS, PLAN_FIELDS, ReviewError, _atomic_write,
    _load_csv, _load_json, _sha, _utc, _validate_review, _write_csv,
)

SCHEMA = "offline-governance-scorecard-v0.7"
PACKAGE_FILES = ("coverage.csv", "dashboard.html", "remediation_actions.csv", "reviewed_changes.csv")
METRIC_FIELDS = ("metric", "label", "numerator", "denominator", "percent", "meaning")
QUEUE_FIELDS = ("change_id", "action_owner", "action_due_utc", "action_status", "due_indicator")


def _metric(name: str, label: str, n: int, d: int, meaning: str) -> dict:
    if not 0 <= n <= d:
        raise ReviewError(f"Invalid scorecard totals: {name}")
    return {"metric":name, "label":label, "numerator":n, "denominator":d,
            "percent":round(100 * n / d, 1) if d else None, "meaning":meaning}


def _verify_package(package: Path) -> tuple[dict, list[dict], list[dict], list[dict], dict]:
    if not package.is_dir() or package.is_symlink():
        raise ReviewError("Evidence package directory must exist and not be a symlink")
    manifest = _load_json(package / "package_manifest.json")
    if manifest.get("schema") != "offline-review-evidence-v0.6" or manifest.get("no_network") is not True:
        raise ReviewError("Expected an offline v0.6 review evidence package")
    expected = manifest.get("output_sha256")
    if not isinstance(expected, dict) or set(expected) != set(PACKAGE_FILES):
        raise ReviewError("Incomplete or unexpected package output digest list")
    for filename in PACKAGE_FILES:
        file = package / filename
        digest = expected[filename]
        if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ReviewError("Invalid SHA-256 digest in source manifest")
        if not file.is_file() or file.is_symlink() or file.stat().st_size > 12_000_000:
            raise ReviewError(f"Missing or unsafe package file: {filename}")
        if not hmac.compare_digest(_sha(file), digest):
            raise ReviewError(f"Package file checksum mismatch: {filename}")
    rows = _load_csv(package / "reviewed_changes.csv", REPORT_FIELDS)
    actions = _load_csv(package / "remediation_actions.csv", ACTION_FIELDS)
    coverage = _load_csv(package / "coverage.csv", COVER_FIELDS)
    if not isinstance(manifest.get("changes"), int) or len(rows) != manifest["changes"]:
        raise ReviewError("Review package change count mismatch")
    if not isinstance(manifest.get("tracked_actions"), int) or len(actions) != manifest["tracked_actions"]:
        raise ReviewError("Review package action count mismatch")
    if not isinstance(manifest.get("coverage_warnings"), int) or sum(c["comparable"] != "yes" for c in coverage) != manifest["coverage_warnings"]:
        raise ReviewError("Review package coverage count mismatch")
    if any(c["comparable"] not in {"yes", "no", "partial"} for c in coverage):
        raise ReviewError("Unknown scope comparability state")
    if not isinstance(manifest.get("review_flags"), dict):
        raise ReviewError("Review package missing disposition flags")
    original_as_of = _utc(manifest.get("as_of_utc"), "package as_of_utc")
    seen, expected_actions = set(), {}
    for row in rows:
        cid = row["change_id"]
        if not cid or cid in seen:
            raise ReviewError("Missing or duplicate review change ID")
        seen.add(cid)
        flag = _validate_review({key: row[key] for key in PLAN_FIELDS}, original_as_of)
        if row["review_flag"] != flag:
            raise ReviewError("Review flag contradicts recorded disposition/date")
        if row["disposition"] in {"investigate", "remediate"}:
            expected_actions[cid] = {key:row[key] for key in ACTION_FIELDS}
    if dict(Counter(r["review_flag"] for r in rows)) != manifest["review_flags"]:
        raise ReviewError("Review flag totals do not match package manifest")
    actual_actions = {}
    for row in actions:
        cid = row["change_id"]
        if cid in actual_actions or cid not in expected_actions or row != expected_actions[cid]:
            raise ReviewError("Remediation action does not match its review record")
        actual_actions[cid] = row
    if set(actual_actions) != set(expected_actions):
        raise ReviewError("Action records missing from evidence package")
    return manifest, rows, actions, coverage, {filename: _sha(package / filename) for filename in PACKAGE_FILES}


def _verify_external_files(directory: Path | None, expected: object, names: tuple[str, ...], label: str) -> str:
    if directory is None:
        return "not_supplied"
    folder = Path(directory).resolve()
    if not folder.is_dir() or not isinstance(expected, dict) or set(expected) != set(names):
        raise ReviewError(f"Missing or incompatible {label} provenance inputs")
    for name in names:
        file = folder / name
        if not file.is_file() or file.is_symlink() or not isinstance(expected[name], str) or not hmac.compare_digest(_sha(file), expected[name]):
            raise ReviewError(f"{label} source checksum mismatch: {name}")
    return "hashes_match"


def _dashboard(score: dict, actions: list[dict], coverage: list[dict]) -> str:
    esc = lambda x: html.escape(str(x), quote=True)
    def table(items: list[dict], keys: tuple[str, ...]) -> str:
        return ("<div class='scroll'><table><thead><tr>" + "".join(f"<th>{esc(k.replace('_',' ').title())}</th>" for k in keys)
                + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{esc(row.get(k,''))}</td>" for k in keys) + "</tr>" for row in items)
                + "</tbody></table></div>")
    cards = "".join("<section class='metric'><div class='percent'>"+ (f"{m['percent']}%" if m["percent"] is not None else "N/A")
                    +"</div><strong>"+esc(m["label"])+"</strong><p>"+esc(m["numerator"])+" of "+esc(m["denominator"])+"</p></section>" for m in score["metrics"])
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<title>Governance Workflow Scorecard</title><style>:root{color-scheme:light}body{font:15px/1.55 system-ui,sans-serif;color:#26323c;max-width:1150px;margin:48px auto;padding:0 22px;background:#fff}h1{letter-spacing:-.04em}h2{margin-top:32px}p,small{color:#576779}.eyebrow{text-transform:uppercase;font-size:11px;letter-spacing:.1em;color:#745c43}"
            ".metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:12px;margin:24px 0}.metric{border:1px solid #d7dddf;border-radius:12px;padding:17px}.metric p{margin:3px 0 0;font-size:12px}.percent{font-size:27px;font-weight:750;color:#253c4d}.notice{padding:14px 18px;border-left:3px solid #a17f58;background:#f6f4ef}"
            ".scroll{overflow-x:auto}table{border-collapse:collapse;width:100%}td,th{padding:10px 12px;border-bottom:1px solid #e0e4e6;text-align:left;font-size:12px;overflow-wrap:anywhere}th{background:#f3f5f6;text-transform:uppercase;font-size:11px}</style></head><body>"
            "<div class='eyebrow'>Offline governance reporting / synthetic demonstration</div><h1>Review Workflow Scorecard</h1>"
            "<p>As of "+esc(score["as_of_utc"])+" · "+esc(score["readiness"].replace("_"," ").title())+"</p>"
            "<div class='notice'><strong>Process indicators only.</strong> This is not an identity security rating, regulatory compliance score or verified approval attestation. The sample review decisions are self-reported. No tenant-wide coverage is implied.</div>"
            "<div class='metrics'>"+cards+"</div><h2>Action follow-up</h2>"
            +table(actions,QUEUE_FIELDS)+"<h2>Collection scope</h2>"+table(coverage,COVER_FIELDS)
            +"<p><small>Only explicitly selected Entra groups and SharePoint sites are represented. Source hashes detect changes within the supplied local package; they are not digital signatures.</small></p></body></html>\n")


def create_scorecard(package: Path, output: Path, as_of: dt.datetime,
                     comparison: Path | None = None, plan: Path | None = None) -> dict:
    """Read a v0.6 package without changing it. Re-evaluate time-sensitive queues."""
    if as_of.tzinfo is None:
        raise ReviewError("--as-of must be timezone-aware")
    now = as_of.astimezone(dt.timezone.utc)
    package = Path(package).resolve()
    manifest, rows, actions, coverage, package_hashes = _verify_package(package)
    packaged_at = _utc(manifest["as_of_utc"], "package as_of_utc")
    if now < packaged_at:
        raise ReviewError("Scorecard --as-of precedes the underlying evidence package")
    source_checks = {
        "comparison": _verify_external_files(comparison, manifest.get("source_comparison_sha256"),
                                             ("changes.csv", "coverage.csv", "manifest.json"), "comparison"),
        "review_plan": _verify_external_files(plan, manifest.get("plan_sha256"),
                                              ("reviews.csv", "source.json"), "review plan"),
    }
    pending = sum(r["disposition"] == "pending" for r in rows)
    active_actions = [a for a in actions if a["action_status"] != "closed"]
    overdue = sum(_utc(a["action_due_utc"], "action_due_utc") < now for a in active_actions)
    closed = sum(a["action_status"] == "closed" for a in actions)
    exceptions = [r for r in rows if r["disposition"] == "exception"]
    current_exceptions = sum(_utc(r["exception_expires_utc"], "exception_expires_utc") >= now for r in exceptions)
    confirmed_coverage = sum(c["comparable"] == "yes" for c in coverage)
    metrics = [
        _metric("documented_review_rate", "Reviews documented", len(rows)-pending, len(rows),
                "Self-reported dispositions present; not independently authenticated"),
        _metric("open_action_timeliness", "Open actions within due date", len(active_actions)-overdue,len(active_actions),
                "Open actions only; closed actions are self-reported and excluded"),
        _metric("exception_currency", "Exceptions not expired", current_exceptions,len(exceptions),
                "Exception approvals are recorded claims, not verified authority"),
        _metric("comparable_collection_scope", "Comparable selected scopes", confirmed_coverage,len(coverage),
                "Comparison coverage among exported selections, not tenant-wide coverage"),
        _metric("closed_action_reference", "Closed actions with references", sum(bool(a["closure_evidence"]) for a in actions if a["action_status"]=="closed"),closed,
                "References are self-reported; their content and validity are not independently verified"),
    ]
    followup = [{"change_id":a["change_id"], "action_owner":a["action_owner"], "action_due_utc":a["action_due_utc"],
                 "action_status":a["action_status"], "due_indicator":("closed_self_reported" if a["action_status"]=="closed" else
                 "overdue" if _utc(a["action_due_utc"], "action_due_utc") < now else "open_within_due_date")}
                for a in actions]
    followup.sort(key=lambda row:(row["due_indicator"] != "overdue",row["action_due_utc"],row["change_id"]))
    if not rows:
        readiness="insufficient_observations"
    elif pending or overdue or current_exceptions != len(exceptions) or any(c["comparable"] != "yes" for c in coverage):
        readiness="attention_required"
    elif active_actions:
        readiness="open_followup_actions"
    else:
        readiness="documented_within_selected_scope"
    report = {"schema":SCHEMA,"mode":"offline","no_network":True,"as_of_utc":now.isoformat(),
              "evidence_package_as_of_utc":packaged_at.isoformat(),"readiness":readiness,
              "metrics":metrics,"counts":{"changes":len(rows),"pending_reviews":pending,"active_actions":len(active_actions),
                                         "overdue_actions":overdue,"closed_actions_self_reported":closed,
                                         "expired_exceptions":len(exceptions)-current_exceptions,
                                         "noncomparable_scopes":len(coverage)-confirmed_coverage},
              "source_validation":source_checks,
              "limitations":["Workflow indicators only, not an enterprise security score or verified compliance assessment",
                             "All reviewer decisions and closure references are self-reported",
                             "Only selected and previously exported identities/sites are represented",
                             "Package digests are integrity checks, not cryptographic attestations"]}
    def build(stage: Path) -> None:
        (stage/"scorecard.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n", encoding="utf-8")
        _write_csv(stage/"scorecard.csv",METRIC_FIELDS,[{**m,"percent":(m["percent"] if m["percent"] is not None else "N/A")} for m in metrics])
        _write_csv(stage/"action_queue.csv",QUEUE_FIELDS,followup)
        (stage/"dashboard.html").write_text(_dashboard(report,followup,coverage),encoding="utf-8")
        out_manifest={"schema":SCHEMA,"no_network":True,"as_of_utc":now.isoformat(),
                      "source_package_manifest_sha256":_sha(package/"package_manifest.json"),
                      "source_package_sha256":package_hashes,"source_checks":source_checks,
                      "output_sha256":{p.name:_sha(p) for p in sorted(stage.iterdir())},
                      "note":"Hashes are reproducibility checks, not signatures or independent verification"}
        (stage/"manifest.json").write_text(json.dumps(out_manifest,indent=2)+"\n",encoding="utf-8")
    inputs = [package] + ([Path(comparison).resolve()] if comparison is not None else []) + ([Path(plan).resolve()] if plan is not None else [])
    _atomic_write(Path(output),inputs,build)
    return report