"""Read-only access-governance checks on normalized CSV snapshots.

Synthetic demo first. This module never connects to a tenant or mutates access.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

SCHEMAS: dict[str, tuple[str, ...]] = {
    "users": ("user_id", "display_name", "user_type", "enabled", "job_role"),
    "groups": ("group_id", "name", "privileged", "owner_id"),
    "memberships": ("group_id", "user_id", "granted_at"),
    "approvals": ("request_id", "user_id", "resource_type", "resource_id", "status", "approved_at", "expires_at"),
    "sites": ("site_id", "name", "sensitivity", "owner_id"),
    "site_permissions": ("site_id", "user_id", "permission", "granted_at"),
    "campaigns": ("campaign_id", "type", "resource_id", "owner_id", "due_date", "status"),
    "audit_events": ("event_id", "source", "request_id", "user_id", "resource_id", "event_type", "occurred_at"),
    "exceptions": ("control_id", "subject", "expires_on", "approved_by", "reason"),
}

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
SUPPORTED_CONTROLS = (
    "PRV-001", "PRV-002", "PRV-003", "PRV-004", "SP-001", "SP-002", "SP-003", "REV-001", "AUD-001"
)


@dataclass(frozen=True)
class Finding:
    control_id: str
    severity: str
    subject: str
    resource: str
    title: str
    detail: str
    recommendation: str
    evidence_keys: tuple[str, ...] = ()
    status: str = "open"
    exception_reason: str = ""
    exception_expires: str = ""

    def to_dict(self) -> dict:
        row = asdict(self)
        row["evidence_keys"] = list(self.evidence_keys)
        return row


@dataclass
class Audit:
    as_of: str
    findings: list[Finding]
    counts: dict[str, int]
    evidence: list[dict]
    input_hashes: dict[str, str]
    records: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "schema_version": "1.0", "as_of": self.as_of,
            "notice": "Snapshot-based heuristic findings; not proof of actual access risk or an exhaustive tenant audit.",
            "counts": self.counts, "source_record_counts": self.records,
            "input_sha256": self.input_hashes,
            "findings": [x.to_dict() for x in self.findings],
            "evidence": self.evidence,
        }


def parse_date(value: str, where: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        raise ValueError(f"Invalid ISO date at {where}: {value!r} (expected YYYY-MM-DD)") from None


def is_true(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes", "y"}


def load_snapshot(folder: Path) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """All columns explicit; fail closed on incomplete/malformed snapshots."""
    folder = Path(folder)
    data: dict[str, list[dict]] = {}
    hashes: dict[str, str] = {}
    for name, columns in SCHEMAS.items():
        file = folder / f"{name}.csv"
        if not file.is_file():
            raise ValueError(f"Missing required file: {file}")
        raw = file.read_bytes()
        hashes[file.name] = hashlib.sha256(raw).hexdigest()
        try:
            with file.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None:
                    raise ValueError(f"Empty or invalid CSV: {file}")
                missing = set(columns) - set(reader.fieldnames)
                if missing:
                    raise ValueError(f"{file.name} missing columns: {', '.join(sorted(missing))}")
                rows = []
                for i, row in enumerate(reader, 2):
                    if None in row or any(v is None for v in row.values()):
                        raise ValueError(f"Malformed CSV row at {file.name}:{i}")
                    rows.append({col: (row[col] or "").strip() for col in columns})
                data[name] = rows
        except UnicodeError:
            raise ValueError(f"{file.name} must be UTF-8") from None

    for table, key in [("users", "user_id"), ("groups", "group_id"), ("sites", "site_id"),
                       ("approvals", "request_id"), ("campaigns", "campaign_id"),
                       ("audit_events", "event_id")]:
        ids = [row[key] for row in data[table]]
        if any(not v for v in ids) or len(ids) != len(set(ids)):
            raise ValueError(f"{table}.csv has duplicate or blank {key}")
    for table, col in [("site_permissions", "granted_at"),
                       ("campaigns", "due_date"), ("audit_events", "occurred_at")]:
        for i, row in enumerate(data[table], 2):
            parse_date(row[col], f"{table}.csv:{i}:{col}")
    for i, row in enumerate(data["memberships"], 2):
        if row["granted_at"]:
            parse_date(row["granted_at"], f"memberships.csv:{i}:granted_at")
    for table, col in [("approvals", "approved_at"), ("approvals", "expires_at"),
                       ("exceptions", "expires_on")]:
        for i, row in enumerate(data[table], 2):
            if row[col]:
                parse_date(row[col], f"{table}.csv:{i}:{col}")
    return data, hashes


def run_checks(data: dict[str, list[dict]], hashes: dict[str, str], as_of: dt.date) -> Audit:
    users = {u["user_id"]: u for u in data["users"]}
    groups = {g["group_id"]: g for g in data["groups"]}
    sites = {s["site_id"]: s for s in data["sites"]}
    approvals = data["approvals"]
    events = data["audit_events"]
    findings: list[Finding] = []
    evidence: list[dict] = []

    def add(control: str, severity: str, subject: str, resource: str, title: str,
            detail: str, recommendation: str, keys: Iterable[str] = ()) -> None:
        findings.append(Finding(control, severity, subject, resource, title, detail,
                                recommendation, tuple(keys)))

    def matching_approvals(user: str, resource_type: str, resource_id: str) -> list[dict]:
        return [a for a in approvals if a["user_id"] == user and
                a["resource_type"].lower() == resource_type and a["resource_id"] == resource_id and
                a["status"].lower() == "approved" and a["approved_at"] and
                parse_date(a["approved_at"], f"approval {a['request_id']}") <= as_of and
                (not a["expires_at"] or parse_date(a["expires_at"], f"approval {a['request_id']}") >= as_of)]

    for group in data["groups"]:
        if is_true(group["privileged"]) and not group["owner_id"]:
            add("PRV-004", "medium", group["group_id"], group["name"],
                "Privileged group has no recorded owner", "The exported group owner field is blank.",
                "Confirm ownership in Entra and update the authoritative inventory.")

    for membership in data["memberships"]:
        group = groups.get(membership["group_id"])
        user = users.get(membership["user_id"])
        if group is None or user is None:
            raise ValueError(f"Membership references unknown group/user: {membership}")
        if not is_true(group["privileged"]):
            continue
        uid, gid = user["user_id"], group["group_id"]
        granted = (parse_date(membership["granted_at"], f"membership {uid}/{gid}")
                   if membership["granted_at"] else None)
        matched = matching_approvals(uid, "group", gid)
        if not matched:
            add("PRV-001", "high", uid, group["name"],
                "Privileged membership lacks a current approval", 
                "No approved, unexpired request for this direct group membership was present in the snapshot.",
                "Locate approval evidence or request an authorized access review; do not automatically revoke.",
                (f"membership:{gid}:{uid}",))
        else:
            earliest = min(matched, key=lambda a: a["approved_at"])
            if granted is not None and parse_date(earliest["approved_at"], f"approval {earliest['request_id']}") > granted:
                add("PRV-002", "high", uid, group["name"],
                    "Approval was recorded after privileged access was granted",
                    f"Membership granted {membership['granted_at']}; approval recorded {earliest['approved_at']}.",
                    "Verify emergency-access exception or investigate the sequence.", (earliest["request_id"],))
            # Intentional, configurable audit-example assumption: both system footprints expected.
            for approval in matched:
                found_iga = [e for e in events if e["source"].lower() == "iga" and
                                   e["request_id"] == approval["request_id"] and e["user_id"] == uid and
                                   e["resource_id"] == gid and e["event_type"] == "approval_recorded"]
                found_siem = [e for e in events if e["source"].lower() == "siem" and
                                  e["request_id"] == approval["request_id"] and e["user_id"] == uid and
                                  e["resource_id"] == gid and e["event_type"] == "membership_change"]
                if found_iga and found_siem:
                    evidence.append({"request_id": approval["request_id"], "user_id": uid, "resource_id": gid,
                                     "iga_events": ";".join(e["event_id"] for e in found_iga),
                                     "siem_events": ";".join(e["event_id"] for e in found_siem),
                                     "status": "correlated"})
                    break
            else:
                # One finding per membership, not per approval candidate.
                add("AUD-001", "medium", uid, group["name"], "Audit evidence correlation incomplete",
                    "No current approval has both a matching IGA approval_recorded event and SIEM membership_change event in this export.",
                    "Verify log coverage, retention, request-ID mapping and export completeness before treating this as a control failure.",
                    tuple(a["request_id"] for a in matched))
        if not is_true(user["enabled"]):
            add("PRV-003", "high", uid, group["name"], "Disabled identity retains privileged membership",
                "The identity is marked disabled but retains a direct privileged group membership.",
                "Confirm current status and removal requirements with the application/group owner.")

    for site in data["sites"]:
        if not site["owner_id"]:
            add("SP-002", "medium", site["site_id"], site["name"],
                "SharePoint site has no recorded owner", "The source export did not identify a site owner.",
                "Validate the site owner in SharePoint and update inventory.")

    for permission in data["site_permissions"]:
        site = sites.get(permission["site_id"])
        user = users.get(permission["user_id"])
        if site is None or user is None:
            raise ValueError(f"Site permission references unknown site/user: {permission}")
        uid, sid = user["user_id"], site["site_id"]
        if not is_true(user["enabled"]):
            add("SP-003", "medium", uid, site["name"], "Disabled identity retains SharePoint permission",
                f"Direct exported site permission: {permission['permission']}.",
                "Validate account status and site permissions; follow approved offboarding process.")
        if user["user_type"].lower() in {"guest", "external"} and site["sensitivity"].lower() in {"confidential", "restricted"}:
            valid = matching_approvals(uid, "site", sid)
            if not valid:
                add("SP-001", "high", uid, site["name"],
                    "External access to sensitive SharePoint site lacks current approval",
                    f"Guest/external identity has {permission['permission']} on a {site['sensitivity']} site without a matching approved site request in the export.",
                    "Validate business sponsor, approved sharing exception and access necessity.")

    for campaign in data["campaigns"]:
        if campaign["status"].lower() not in {"completed", "closed"} and parse_date(campaign["due_date"], "campaign due_date") < as_of:
            add("REV-001", "medium", campaign["campaign_id"], campaign["resource_id"],
                "Access-review campaign overdue",
                f"{campaign['type']} campaign due {campaign['due_date']} is {campaign['status']}.",
                "Contact the campaign owner, document the blocker, and obtain review completion evidence.")

    # Exceptions are exact-match and time-bounded; expired exceptions do not suppress findings.
    configured: dict[tuple[str, str], dict] = {}
    for exc in data["exceptions"]:
        if exc["control_id"] not in SUPPORTED_CONTROLS:
            raise ValueError(f"Unknown exception control: {exc['control_id']}")
        if not exc["approved_by"] or not exc["reason"] or not exc["expires_on"]:
            raise ValueError("Exceptions require approved_by, reason and expires_on")
        key = (exc["control_id"], exc["subject"])
        if key in configured:
            raise ValueError(f"Duplicate exception for {key}")
        configured[key] = exc
    from dataclasses import replace
    filtered = []
    for finding in findings:
        exc = configured.get((finding.control_id, finding.subject))
        if exc and parse_date(exc["expires_on"], "exception") >= as_of:
            filtered.append(replace(finding, status="excepted", exception_reason=exc["reason"],
                                    exception_expires=exc["expires_on"]))
        else:
            filtered.append(finding)
    filtered.sort(key=lambda f: (f.status != "open", SEVERITY_ORDER[f.severity], f.control_id, f.subject))
    counts = {
        "open": sum(f.status == "open" for f in filtered),
        "excepted": sum(f.status == "excepted" for f in filtered),
        "high": sum(f.severity == "high" and f.status == "open" for f in filtered),
        "medium": sum(f.severity == "medium" and f.status == "open" for f in filtered),
        "correlated_evidence": len(evidence),
        "controls_evaluated": len(SUPPORTED_CONTROLS),
    }
    return Audit(as_of.isoformat(), filtered, counts, evidence, hashes, {k: len(v) for k, v in data.items()})


def analyze(folder: Path, as_of: dt.date) -> Audit:
    data, hashes = load_snapshot(folder)
    return run_checks(data, hashes, as_of)