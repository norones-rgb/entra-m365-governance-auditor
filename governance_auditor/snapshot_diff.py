"""Offline, coverage-aware drift comparison for selected Entra and SharePoint exports.

Reports changes in observed direct assignments, not effective permissions,
confirmed revocations, valid approvals, or tenant-wide security posture.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import html
import json
import shutil
import tempfile
import uuid
from collections import Counter
from pathlib import Path


class ComparisonError(ValueError):
    """Incomplete, incompatible, or potentially misleading input."""


MAX_ROWS = 100_000
MAX_FILE_BYTES = 12_000_000
CHANGE_FIELDS = ("system", "category", "change", "resource", "principal", "before", "after", "interpretation")
COVER_FIELDS = ("system", "scope", "before", "after", "comparable", "note")
GRAPH_FILES = {
    "groups.csv": ("group_id", "name", "privileged", "owner_id"),
    "users.csv": ("user_id", "enabled"),
    "memberships.csv": ("group_id", "user_id"),
    "non_user_members.csv": ("group_id", "member_id", "odata_type"),
}
SHAREPOINT_FILES = {
    "sharepoint_group_members.csv": ("site_url", "sharepoint_group", "principal_login", "principal_type"),
    "site_collection_admins.csv": ("site_url", "principal_login", "principal_type"),
    "root_web_role_assignments.csv": ("site_url", "principal_login", "principal_type", "role_names"),
}


def _csv(folder: Path, filename: str, required: tuple[str, ...]) -> list[dict]:
    path = folder / filename
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_FILE_BYTES:
        raise ComparisonError(f"Missing, oversized, or unsafe input: {filename}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rdr = csv.DictReader(handle)
        if not rdr.fieldnames or len(set(rdr.fieldnames)) != len(rdr.fieldnames) or not set(required).issubset(rdr.fieldnames):
            raise ComparisonError(f"Invalid columns in {filename}")
        rows = []
        for row in rdr:
            if len(rows) >= MAX_ROWS or None in row or any(value is None for value in row.values()):
                raise ComparisonError(f"Malformed/oversized input in {filename}")
            rows.append(row)
        return rows


def _manifest(folder: Path, prefix: str) -> dict:
    path = folder / "manifest.json"
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 100_000:
        raise ComparisonError("Missing or unsafe source manifest.json")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError):
        raise ComparisonError("Malformed source manifest") from None
    if not isinstance(value, dict) or not str(value.get("schema", "")).startswith(prefix):
        raise ComparisonError("Incompatible source manifest schema")
    try:
        timestamp = dt.datetime.fromisoformat(value["collected_at_utc"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("naive timestamp")
        value["_collected"] = timestamp.astimezone(dt.timezone.utc)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ComparisonError("Missing or invalid timezone-aware collection timestamp") from None
    return value


def _guid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise ComparisonError("Malformed Graph object ID") from None


def _unique(rows: list[dict], keys: tuple[str, ...], filename: str) -> dict:
    result = {}
    for row in rows:
        key = tuple(row[col].strip().casefold() for col in keys)
        if any(not x for x in key) or key in result:
            raise ComparisonError(f"Empty or duplicate key in {filename}")
        result[key] = row
    return result


def _graph(folder: Path) -> dict:
    manifest = _manifest(folder, "graph-partial-v0.2")
    data = {f: _csv(folder, f, fields) for f, fields in GRAPH_FILES.items()}
    groups = _unique(data["groups.csv"], ("group_id",), "groups.csv")
    users = _unique(data["users.csv"], ("user_id",), "users.csv")
    members = _unique(data["memberships.csv"], ("group_id", "user_id"), "memberships.csv")
    other = _unique(data["non_user_members.csv"], ("group_id", "member_id"), "non_user_members.csv")
    ids = {_guid(r["group_id"]) for r in data["groups.csv"]}
    selected = manifest.get("group_ids")
    if not isinstance(selected, list) or len(selected) != len(set(selected)) or {_guid(x) for x in selected} != ids:
        raise ComparisonError("Graph manifest group scope does not match groups.csv")
    for row in data["users.csv"]:
        _guid(row["user_id"])
        if row["enabled"].casefold() not in ("true", "false"):
            raise ComparisonError("Unclassified user account status")
    for row in data["memberships.csv"]:
        if (row["group_id"].casefold(),) not in groups or (row["user_id"].casefold(),) not in users:
            raise ComparisonError("Direct membership references missing group or user")
    for row in data["non_user_members.csv"]:
        if (row["group_id"].casefold(),) not in groups:
            raise ComparisonError("Non-user member references missing group")
        _guid(row["member_id"])
    return {"manifest": manifest, "groups": groups, "users": users, "members": members, "non_users": other, "ids": ids}


def _sharepoint(folder: Path) -> dict:
    manifest = _manifest(folder, "pnp-sharepoint-v0.3")
    site = str(manifest.get("site_url", "")).strip().rstrip("/").casefold()
    if not site.startswith("https://"):
        raise ComparisonError("Invalid SharePoint site scope")
    data = {f: _csv(folder, f, fields) for f, fields in SHAREPOINT_FILES.items()}
    for rows in data.values():
        for row in rows:
            if row["site_url"].strip().rstrip("/").casefold() != site:
                raise ComparisonError("SharePoint record belongs to a different site")
    group_rows = data["sharepoint_group_members.csv"]
    for row in group_rows:
        if not (row.get("sharepoint_group_id", "").strip() or row["sharepoint_group"].strip()):
            raise ComparisonError("SharePoint roster group key is missing")
    # Identity is rooted in the selected site and the exported SharePoint group.
    group_keys = lambda r: (r.get("sharepoint_group_id", "").strip() or r["sharepoint_group"].strip()).casefold()
    roster = {}
    for r in group_rows:
        key = (group_keys(r), r["principal_login"].strip().casefold(), r["principal_type"].strip().casefold())
        if not all(key) or key in roster:
            raise ComparisonError("Duplicate or missing SharePoint roster identity")
        roster[key] = r
    admins = _unique(data["site_collection_admins.csv"], ("principal_login", "principal_type"), "site_collection_admins.csv")
    roles = {}
    for row in data["root_web_role_assignments.csv"]:
        login = row["principal_login"].strip().casefold()
        typ = row["principal_type"].strip().casefold()
        names = [x.strip().casefold() for x in row["role_names"].split(";") if x.strip()]
        if not login or not typ or len(names) != len(set(names)):
            raise ComparisonError("Invalid/duplicate role assignment")
        for role in names:
            key = (login, typ, role)
            if key in roles:
                raise ComparisonError("Duplicate root-web role assignment")
            roles[key] = row
    return {"manifest": manifest, "site": site, "roster": roster, "admins": admins, "roles": roles}


def _safe_csv(value: object) -> str:
    value = str(value if value is not None else "")
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def _write_csv(path: Path, rows: list[dict], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _safe_csv(row.get(field, "")) for field in fields})


def _html(changes: list[dict], coverage: list[dict]) -> str:
    e = lambda x: html.escape(str(x), quote=True)
    count = Counter(r["change"] for r in changes)
    tr = lambda row, fields: "<tr>" + "".join("<td>" + e(row.get(k, "")) + "</td>" for k in fields) + "</tr>"
    change_rows = "".join(tr(row, CHANGE_FIELDS) for row in changes)
    cover_rows = "".join(tr(row, COVER_FIELDS) for row in coverage)
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Access Snapshot Drift</title><style>body{font:15px system-ui,sans-serif;color:#20262c;max-width:1220px;margin:3rem auto;padding:0 1rem;}"
            ".stats{display:flex;gap:1rem;flex-wrap:wrap}.stat{border:1px solid #d6d6d6;border-radius:9px;padding:1rem;min-width:120px}"
            "table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:.65rem;border-bottom:1px solid #ddd;overflow-wrap:anywhere}"
            "th{background:#f5f4ef}main{overflow-x:auto}small{color:#61656c}</style></head><body>"
            "<h1>Entra / SharePoint Change Comparison</h1><p><small>Offline and scope-limited. A change in exported observations "
            "is not proof of effective access, valid authorization, or actual revocation. No live connections.</small></p>"
            + f"<div class='stats'><div class='stat'><b>{len(changes)}</b><br>observed changes</div><div class='stat'><b>{count['added']}</b><br>added</div>"
            + f"<div class='stat'><b>{count['removed']}</b><br>removed</div><div class='stat'><b>{sum(c['comparable'] != 'yes' for c in coverage)}</b><br>coverage warnings</div></div>"
            + "<h2>Changes in comparable scopes</h2><main><table><thead><tr>"
            + "".join("<th>" + e(name.replace("_", " ").title()) + "</th>" for name in CHANGE_FIELDS) + "</tr></thead><tbody>"
            + change_rows + "</tbody></table></main><h2>Scope / collection coverage</h2><main><table><thead><tr>"
            + "".join("<th>" + e(name.replace("_", " ").title()) + "</th>" for name in COVER_FIELDS) + "</tr></thead><tbody>"
            + cover_rows + "</tbody></table></main><p><small>Only selected direct Entra memberships, user status, and exported SharePoint root-site records. "
            "No nested effective membership, inheritance, list/item access, sharing links, approval verification, or automatic remediation.</small></p>"
            "</body></html>\n")


def _comparables(before: dict, after: dict, system: str, category: str, desc: str,
                 allowed: set, changes: list[dict], interpretation: str, mapping: callable | None = None) -> None:
    b = before
    a = after
    for key in sorted(set(b) ^ set(a)):
        if not allowed(key):
            continue
        value = (a if key in a else b)[key]
        resource, principal, context = mapping(key, value) if mapping else (str(key[0]), str(key[1]), "")
        changes.append({"system": system, "category": category, "change": "added" if key in a else "removed",
                        "resource": resource, "principal": principal,
                        "before": context if key in b else "", "after": context if key in a else "",
                        "interpretation": interpretation})


def _source_hashes(dirs: list[Path]) -> dict:
    out = {}
    for label, folder in zip(("before_graph", "after_graph", "before_sharepoint", "after_sharepoint"), dirs):
        if folder is None:
            continue
        out[label] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file() and not p.is_symlink() and p.suffix in (".csv", ".json")}
    return out


def compare_snapshots(before_graph: Path, after_graph: Path, output: Path,
                      before_sharepoint: Path | None = None, after_sharepoint: Path | None = None) -> dict:
    """Compare selected Graph exports, optionally adding one matched SharePoint site pair."""
    if (before_sharepoint is None) != (after_sharepoint is None):
        raise ComparisonError("Provide both before and after SharePoint directories, or neither")
    bg, ag, output = (Path(p).resolve() for p in (before_graph, after_graph, output))
    bs = Path(before_sharepoint).resolve() if before_sharepoint else None
    ass = Path(after_sharepoint).resolve() if after_sharepoint else None
    dirs = [bg, ag] + ([bs, ass] if bs and ass else [])
    if len(set(dirs)) != len(dirs) or any(not p.is_dir() for p in dirs):
        raise ComparisonError("All before/after snapshot inputs must be distinct existing directories")
    if output.exists() or any(output == p or output.is_relative_to(p) or p.is_relative_to(output) for p in dirs):
        raise ComparisonError("Output must be a fresh directory outside the input trees")
    before, after = _graph(bg), _graph(ag)
    if before["manifest"]["_collected"] >= after["manifest"]["_collected"]:
        raise ComparisonError("After Graph snapshot must have a later timestamp")
    changes, coverage = [], []
    selected_b, selected_a = before["ids"], after["ids"]
    common = selected_b & selected_a
    for group_id in sorted(selected_b | selected_a):
        present_b, present_a = group_id in selected_b, group_id in selected_a
        coverage.append({"system": "Entra", "scope": group_id, "before": "selected" if present_b else "not selected",
                         "after": "selected" if present_a else "not selected", "comparable": "yes" if present_b and present_a else "no",
                         "note": "Direct membership can be compared" if present_b and present_a else "Changed selection; do not infer access grant/removal"})
    common_check = lambda key: key[0] in common
    for field, cat, note, key_transform in (
        ("members", "direct_user_membership", "Observed direct user group membership, not proof of effective access", lambda k,v:(k[0],k[1],"user")),
        ("non_users", "direct_non_user_member", "Non-user directory object observed; effective rights unknown",lambda k,v:(k[0],k[1],v.get("odata_type", ""))),
    ):
        _comparables(before[field], after[field], "Entra", cat, "", common_check, changes, note, key_transform)
    # Only compare users seen on both sides. A user disappearing outside selected memberships is a coverage change, not proof of deletion.
    for user_key in sorted(set(before["users"]) & set(after["users"])):
        a, b = after["users"][user_key]["enabled"].lower(), before["users"][user_key]["enabled"].lower()
        if a != b:
            changes.append({"system":"Entra", "category":"account_status", "change":"changed", "resource":"selected user status",
                            "principal":user_key[0], "before":b, "after":a,
                            "interpretation":"Observed account status change in selected export, not an access review decision"})
    for group in sorted(common):
        key = (group,)
        b, a = before["groups"][key], after["groups"][key]
        for column in ("privileged", "owner_id", "name"):
            if b[column] != a[column]:
                changes.append({"system":"Entra","category":"group_metadata", "change":"changed", "resource":group,
                                "principal":column,"before":b[column],"after":a[column],
                                "interpretation":"Group metadata/first-listed owner hint; not an attested ownership review"})
    coverage.append({"system":"Entra", "scope":"selected users", "before":str(len(before["users"])),
                     "after":str(len(after["users"])), "comparable":"partial", "note":"Users are only enumerated through selected direct group memberships"})
    if bs and ass:
        sb, sa = _sharepoint(bs), _sharepoint(ass)
        if sb["manifest"]["_collected"] >= sa["manifest"]["_collected"]:
            raise ComparisonError("After SharePoint snapshot must have a later timestamp")
        same_site = sb["site"] == sa["site"]
        coverage.append({"system":"SharePoint", "scope":sb["site"] if same_site else "site selection", "before":sb["site"],
                         "after":sa["site"], "comparable":"yes" if same_site else "no",
                         "note":"Root-site observation only" if same_site else "Different sites; no access changes inferred"})
        if same_site:
            _comparables(sb["roster"], sa["roster"], "SharePoint", "group_roster", "", lambda k:True,
                         changes, "SharePoint group roster observation only; not calculated effective access",
                         lambda k,v:(sb["site"]+" / "+k[0],k[1],k[2]))
            _comparables(sb["admins"], sa["admins"], "SharePoint", "site_collection_admin", "", lambda k:True,
                         changes, "Site collection administrator listing only",
                         lambda k,v:(sb["site"],k[0],k[1]))
            _comparables(sb["roles"], sa["roles"], "SharePoint", "root_web_role", "", lambda k:True,
                         changes, "Root-web role binding only; does not prove list/item effective access",
                         lambda k,v:(sb["site"]+" / "+k[2],k[0],k[1]))
    changes.sort(key=lambda c:(c["system"],c["category"],c["resource"],c["principal"],c["change"]))
    manifest = {"schema":"selected-access-change-v0.5", "mode":"offline", "no_network":True,
                "before_graph_collected_at_utc":before["manifest"]["_collected"].isoformat(),
                "after_graph_collected_at_utc":after["manifest"]["_collected"].isoformat(),
                "sharepoint_included":bool(bs),"changes":len(changes),
                "change_counts":dict(Counter(x["change"] for x in changes)),
                "non_comparable_scopes":sum(x["comparable"]=="no" for x in coverage),
                "coverage":coverage,"source_sha256":_source_hashes([bg,ag,bs,ass]),
                "limitations":["Only explicitly selected direct Entra group memberships and user status", "Selected SharePoint site group rosters, admins and root-web role bindings only",
                               "No transitive/effective permissions, sharing links, list/item access, approval verification, access grant dates, or evidence of revocation",
                               "Scope differences suppress access-change comparisons for non-overlapping groups/sites", "No live tenant connections or account modifications"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".drift-staging-",dir=output.parent))
    try:
        _write_csv(stage/"changes.csv", changes, CHANGE_FIELDS)
        _write_csv(stage/"coverage.csv", coverage, COVER_FIELDS)
        (stage/"manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        (stage/"dashboard.html").write_text(_html(changes,coverage),encoding="utf-8")
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return manifest
