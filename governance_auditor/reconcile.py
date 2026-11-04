"""Offline, evidence-limited reconciliation of selected SharePoint and Entra snapshots.

No network connections; never calculates effective SharePoint permissions.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import re
import shutil
import tempfile
import uuid
from collections import Counter, defaultdict
from pathlib import Path


class ReconcileError(ValueError):
    """A source export is inconsistent or lacks evidence required for correlation."""


SOURCE_FILES = (
    ("sharepoint_group_members.csv", "sharepoint_group_member", ("site_url", "principal_login", "principal_email", "principal_type", "sharepoint_group")),
    ("site_collection_admins.csv", "site_collection_admin", ("site_url", "principal_login", "principal_email", "principal_type")),
    ("root_web_role_assignments.csv", "root_web_role_assignment", ("site_url", "principal_login", "principal_type", "role_names")),
)
RESULT_FIELDS = ("source_view", "site_url", "principal_login", "principal_email", "principal_type", "access_context",
                 "resolution", "method", "directory_kind", "directory_id", "account_enabled", "review_indicator")
EMAIL = re.compile(r"^[^@\s|]+@[^@\s|]+\.[^@\s|]+$", re.IGNORECASE)
CLAIM_EMAIL = re.compile(r"^i:0#\.f\|membership\|([^|]+)$", re.IGNORECASE)
CLAIM_GROUP = re.compile(r"^c:0(?:o\.c\|federateddirectoryclaimprovider|t\.c\|tenant)\|([a-f0-9-]{36})$", re.IGNORECASE)
MAX_ROWS = 100_000


def _read_csv(folder: Path, filename: str, fields: tuple[str, ...]) -> list[dict]:
    path = folder / filename
    if not path.is_file() or path.is_symlink():
        raise ReconcileError(f"Missing or unsafe input file: {filename}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or len(set(reader.fieldnames)) != len(reader.fieldnames) or any(x not in reader.fieldnames for x in fields):
            raise ReconcileError(f"Invalid CSV headers in {filename}")
        rows = []
        for row in reader:
            if len(rows) >= MAX_ROWS or None in row or any(v is None for v in row.values()):
                raise ReconcileError(f"Malformed or oversized CSV: {filename}")
            rows.append(row)
        return rows


def _manifest(folder: Path, schema_prefix: str) -> dict:
    path = folder / "manifest.json"
    if not path.is_file() or path.is_symlink():
        raise ReconcileError("Both inputs must include a provenance manifest.json")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError):
        raise ReconcileError("Unparseable source provenance manifest") from None
    if not isinstance(parsed, dict) or not str(parsed.get("schema", "")).startswith(schema_prefix):
        raise ReconcileError("Incorrect source manifest schema; expected Graph groups and PnP selected-site exports")
    return parsed


def _iso_utc(raw: object) -> dt.datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        value = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value.astimezone(dt.timezone.utc) if value.tzinfo else None


def _normal_alias(raw: str) -> str | None:
    value = raw.strip().casefold()
    return value if EMAIL.fullmatch(value) else None


def _guid(raw: str) -> str | None:
    try:
        return str(uuid.UUID(raw))
    except (TypeError, AttributeError, ValueError):
        return None


def _identity_from_login(login: str) -> tuple[str | None, str | None]:
    login = login.strip()
    if m := CLAIM_GROUP.fullmatch(login):
        return "guid", _guid(m.group(1))
    if value := _guid(login):
        return "guid", value
    if m := CLAIM_EMAIL.fullmatch(login):
        return "alias", _normal_alias(m.group(1))
    if value := _normal_alias(login):
        return "alias", value
    return None, None


def _safe_csv(value: object) -> str:
    value = str(value if value is not None else "")
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def _export_csv(path: Path, rows: list[dict], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows([{x: _safe_csv(row.get(x, "")) for x in fields} for row in rows])


def _render(rows: list[dict], provenance: dict) -> str:
    counter = Counter(r["resolution"] for r in rows)
    count = sum(r["review_indicator"] == "disabled_account_in_exported_assignment" for r in rows)
    def e(v):
        return html.escape(str(v), quote=True)
    lines = []
    for r in rows:
        values = [r["source_view"], r["principal_login"], r["resolution"], r["directory_kind"], r["review_indicator"]]
        lines.append("<tr>" + "".join(f"<td>{e(x)}</td>" for x in values) + "</tr>")
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>SharePoint / Entra Reconciliation</title><style>body{font:15px system-ui,sans-serif;max-width:1150px;margin:3rem auto;padding:0 1rem;color:#20252c}"
            ".stats{display:flex;flex-wrap:wrap;gap:1rem}.stat{border:1px solid #dadada;border-radius:9px;padding:1rem;min-width:130px}"
            "table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;text-align:left;padding:.7rem}th{background:#f3f2ee}"
            "small{color:#5a606b}main{overflow-x:auto}</style></head><body><h1>SharePoint / Entra Identity Reconciliation</h1>"
            "<p><small>Offline, selected-source correlation only. These are observed principal assignments, NOT calculated effective permissions, access approvals, or confirmed security violations.</small></p>"
            f"<div class='stats'><div class='stat'><b>{len(rows)}</b><br>observations</div><div class='stat'><b>{counter['matched']}</b><br>matched</div>"
            f"<div class='stat'><b>{counter['ambiguous'] + counter['unresolved'] + counter['out_of_scope']}</b><br>unresolved / out of scope</div>"
            f"<div class='stat'><b>{count}</b><br>disabled-account review indicators</div></div>"
            "<main><table><thead><tr><th>Source view</th><th>Principal</th><th>Resolution</th><th>Directory kind</th><th>Review indicator</th></tr></thead><tbody>"
            + "".join(lines) + "</tbody></table></main>"
            f"<p><small>Source time difference: {e(provenance.get('source_time_difference_hours', 'unknown'))} hours. "
            "No nested group expansion, list/item-level access, sharing links, historical access grants, or approval evidence is represented. "
            "Treat any real reports as sensitive identity and security data.</small></p></body></html>\n")


def reconcile(graph_dir: Path, sharepoint_dir: Path, output: Path) -> dict:
    """Reconcile two authorized local export directories into a fresh local report."""
    graph_dir, sharepoint_dir, output = map(lambda x: Path(x).resolve(), (graph_dir, sharepoint_dir, output))
    if graph_dir == sharepoint_dir or not graph_dir.is_dir() or not sharepoint_dir.is_dir():
        raise ReconcileError("Specify two different existing source export directories")
    if output.exists() or any(output.is_relative_to(p) for p in (graph_dir, sharepoint_dir)):
        raise ReconcileError("Output must be a fresh directory outside source input directories")
    gmeta = _manifest(graph_dir, "graph-partial-v0.2")
    smeta = _manifest(sharepoint_dir, "pnp-sharepoint-v0.3")
    gusers = _read_csv(graph_dir, "users.csv", ("user_id", "user_type", "enabled"))
    ggroups = _read_csv(graph_dir, "groups.csv", ("group_id", "name"))
    # Historical v0.2 snapshots can be inspected, but will have fewer matchable user aliases.
    aliases = _read_csv(graph_dir, "identity_aliases.csv", ("user_id", "alias_type", "alias_value")) if (graph_dir / "identity_aliases.csv").exists() else []
    group_ids = set()
    users = {}
    for row in gusers:
        uid = _guid(row["user_id"])
        if not uid or uid in users or row["enabled"].lower() not in ("true", "false"):
            raise ReconcileError("Duplicate, invalid, or incompletely classified Graph user")
        users[uid] = row
    for row in ggroups:
        gid = _guid(row["group_id"])
        if not gid or gid in group_ids or gid in users:
            raise ReconcileError("Duplicate or invalid Graph group ID")
        group_ids.add(gid)
    alias_map: dict[str, set[str]] = defaultdict(set)
    for alias in aliases:
        uid, label = _guid(alias["user_id"]), alias["alias_type"]
        if uid not in users or label not in ("upn", "mail"):
            raise ReconcileError("Graph alias has unknown user or unsupported alias type")
        norm = _normal_alias(alias["alias_value"])
        if norm is None:
            raise ReconcileError("Graph alias must be a complete email-shaped UPN or address")
        alias_map[norm].add(uid)
    observations: list[dict] = []
    site_url = smeta.get("site_url", "")
    for filename, source, fields in SOURCE_FILES:
        for item in _read_csv(sharepoint_dir, filename, fields):
            if not site_url or item["site_url"].strip().rstrip("/").casefold() != str(site_url).rstrip("/").casefold():
                raise ReconcileError("SharePoint CSV has a site URL inconsistent with manifest")
            login, email = item["principal_login"].strip(), item.get("principal_email", "").strip()
            typ = item.get("principal_type", "").strip()
            kind, value = _identity_from_login(login)
            matches: set[str] = set()
            method = ""
            resolution = "unresolved"
            match_kind = ""
            match_id = ""
            enabled = ""
            # SharePoint-local groups cannot be matched to Entra users from a group title.
            if "sharepointgroup" in typ.casefold():
                resolution = "out_of_scope"
                method = "local_sharepoint_group"
            elif kind == "guid" and value:
                method = "object_id"
                if value in users:
                    matches = {value}
                    match_kind = "user"
                elif value in group_ids:
                    matches = {value}
                    match_kind = "group"
                else:
                    resolution = "out_of_scope"
            else:
                if kind == "alias" and value:
                    matches.update(alias_map.get(value, set()))
                    method = "login_upn"
                second = _normal_alias(email) if email else None
                if second:
                    matches.update(alias_map.get(second, set()))
                    if not method:
                        method = "email"
                if kind is None and not second:
                    method = "unrecognized_principal"
                match_kind = "user"
            if matches:
                if len(matches) > 1 or (match_kind == "group" and "user" in typ.casefold()) or (match_kind == "user" and "securitygroup" in typ.casefold()):
                    resolution = "ambiguous"
                else:
                    match_id = next(iter(matches))
                    resolution = "matched"
                    if match_kind == "user":
                        enabled = users[match_id]["enabled"].lower()
            context = item.get("sharepoint_group", item.get("role_names", ""))
            observations.append({
                "source_view": source, "site_url": item["site_url"], "principal_login": login,
                "principal_email": email, "principal_type": typ, "access_context": context,
                "resolution": resolution, "method": method, "directory_kind": match_kind if resolution == "matched" else "",
                "directory_id": match_id, "account_enabled": enabled,
                "review_indicator": "disabled_account_in_exported_assignment" if resolution == "matched" and match_kind == "user" and enabled == "false" else "",
            })
    if len(observations) > MAX_ROWS:
        raise ReconcileError("Too many SharePoint observations")
    gtime, stime = _iso_utc(gmeta.get("collected_at_utc")), _iso_utc(smeta.get("collected_at_utc"))
    gap = round(abs((gtime - stime).total_seconds()) / 3600, 2) if gtime and stime else None
    counts = dict(Counter(item["resolution"] for item in observations))
    manifest = {
        "schema": "sp-entra-reconciliation-v0.4", "source": "Offline CSV correlation, no network access",
        "site_url": site_url, "source_schemas": [gmeta["schema"], smeta["schema"]],
        "source_time_difference_hours": gap, "source_time_gap_gt_72_hours": gap > 72 if gap is not None else None,
        "observation_count": len(observations), "resolution_counts": {x: counts.get(x, 0) for x in ("matched", "ambiguous", "unresolved", "out_of_scope")},
        "disabled_account_review_indicators": sum(row["review_indicator"] != "" for row in observations),
        "alias_coverage": "Only aliases from selected Graph users; older exports may contain no aliases.",
        "limitations": ["Not effective permissions or confirmed violations", "Selected Graph groups, direct members only", "Root-web roles, not child resources",
                        "No SharePoint local-group role expansion", "No cross-tenant identity verification", "No approval history, grant dates or review outcomes"],
        "privacy_warning": "Report includes login/email/identity information; never commit real report outputs to public source control.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".reconcile-staging-", dir=output.parent))
    try:
        _export_csv(stage / "identity_matches.csv", observations, RESULT_FIELDS)
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (stage / "dashboard.html").write_text(_render(observations, manifest), encoding="utf-8")
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return manifest