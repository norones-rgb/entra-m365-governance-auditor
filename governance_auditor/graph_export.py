"""Read-only Microsoft Graph v1.0 Entra group snapshot exporter.

Never mutates tenant state. Only explicitly selected group IDs are queried.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
SCOPES = ["Group.Read.All", "User.Read.All"]
MAX_PAGES = 200
MAX_ATTEMPTS = 4


class GraphExportError(ValueError):
    """An incomplete Graph export is not usable as audit evidence."""


def valid_guid(value: str, label: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise GraphExportError(f"{label} must be a GUID") from None


def _safe_url(url: str) -> None:
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.netloc != "graph.microsoft.com" or
            not parts.path.startswith("/v1.0/") or parts.username or parts.password or
            parts.fragment):
        raise GraphExportError("Refused unexpected Graph API URL or pagination host")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request_json(url: str, token: str) -> dict:
    request = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, method="GET")
    with build_opener(_NoRedirect()).open(request, timeout=25) as response:
        try:
            data = json.load(response)
        except (ValueError, UnicodeError):
            raise GraphExportError("Graph returned invalid JSON; export aborted") from None
    if not isinstance(data, dict):
        raise GraphExportError("Graph returned an invalid JSON response")
    return data


class GraphClient:
    def __init__(self, token: str, request_json: Callable[[str, str], dict] | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        if not token:
            raise GraphExportError("A delegated access token is required")
        self._token = token
        self._request = request_json or _request_json
        self._sleep = sleep

    def get(self, url: str) -> dict:
        if url.startswith("/"):
            url = GRAPH_ROOT + url
        _safe_url(url)
        for attempt in range(MAX_ATTEMPTS):
            try:
                result = self._request(url, self._token)
                if not isinstance(result, dict):
                    raise GraphExportError("Graph returned an invalid JSON response")
                return result
            except HTTPError as exc:
                if exc.code in (429, 502, 503, 504) and attempt < MAX_ATTEMPTS - 1:
                    raw = exc.headers.get("Retry-After", "") if exc.headers else ""
                    delay = float(raw) if re.fullmatch(r"\d+(\.\d+)?", raw) else float(2 ** attempt)
                    self._sleep(min(delay, 30.0))
                    continue
                raise GraphExportError(f"Graph request failed (HTTP {exc.code}); export aborted") from None
            except (URLError, TimeoutError):
                raise GraphExportError("Graph request could not be completed; export aborted") from None
        raise GraphExportError("Graph request failed after retries")

    def pages(self, path: str) -> list[dict]:
        results: list[dict] = []
        seen: set[str] = set()
        link = path
        while link:
            if len(seen) >= MAX_PAGES:
                raise GraphExportError("Graph pagination exceeded safety limit")
            full = GRAPH_ROOT + link if link.startswith("/") else link
            _safe_url(full)
            if full in seen:
                raise GraphExportError("Graph returned a pagination loop")
            seen.add(full)
            payload = self.get(full)
            value = payload.get("value")
            if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
                raise GraphExportError("Graph returned a malformed collection")
            results.extend(value)
            link = payload.get("@odata.nextLink", "")
            if link and not isinstance(link, str):
                raise GraphExportError("Graph returned a malformed nextLink")
        return results


def acquire_delegated_token(tenant_id: str, client_id: str, scopes: list[str] | None = None) -> str:
    """MSAL device-code sign-in; no secrets or persistent token cache."""
    try:
        import msal
    except ImportError:
        raise GraphExportError("Install optional authentication dependency: pip install -r requirements-graph.txt") from None
    app = msal.PublicClientApplication(client_id, authority=f"https://login.microsoftonline.com/{tenant_id}")
    flow = app.initiate_device_flow(scopes=scopes if scopes is not None else SCOPES)
    if "user_code" not in flow:
        raise GraphExportError("Microsoft sign-in could not begin; check app registration and delegated permissions")
    print(flow.get("message", "Complete the Microsoft device-code sign-in."))
    result = app.acquire_token_by_device_flow(flow)
    token = result.get("access_token", "")
    if not token:
        raise GraphExportError(f"Microsoft sign-in failed ({result.get('error', 'no_token')}); no export written")
    return token


def _require_id(item: dict, what: str) -> str:
    value = item.get("id")
    if not isinstance(value, str) or not value:
        raise GraphExportError(f"Graph returned a {what} without an ID")
    return value


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def export_snapshot(client: GraphClient, group_ids: list[str], privileged_ids: set[str], output: Path) -> dict:
    """Write a partial snapshot with provenance, never fabricated grant dates or approvals.

    The requested output path must be absent; only a complete export is renamed into place.
    """
    group_ids = [valid_guid(g, "group ID") for g in group_ids]
    privileged_ids = {valid_guid(g, "privileged group ID") for g in privileged_ids}
    if not group_ids or len(group_ids) != len(set(group_ids)):
        raise GraphExportError("Specify unique, explicitly selected group IDs")
    if not privileged_ids.issubset(set(group_ids)):
        raise GraphExportError("Every privileged group must also be selected with --group-id")
    output = Path(output).resolve()
    if output.exists():
        raise GraphExportError("Output path already exists; choose a fresh directory")
    users: dict[str, dict] = {}
    groups: list[dict] = []
    memberships: list[dict] = []
    non_users: list[dict] = []
    owner_counts: dict[str, int] = {}
    dynamic_groups: list[str] = []
    for gid in group_ids:
        item = client.get(f"/groups/{quote(gid)}?$select=id,displayName,groupTypes")
        if _require_id(item, "group") != gid:
            raise GraphExportError("Graph returned a group ID different from the requested group")
        owners = client.pages(f"/groups/{quote(gid)}/owners")
        owner_ids = sorted({_require_id(owner, "owner") for owner in owners})
        owner_counts[gid] = len(owner_ids)
        if "DynamicMembership" in (item.get("groupTypes") or []):
            dynamic_groups.append(gid)
        groups.append({"group_id": gid, "name": item.get("displayName") or gid,
                       "privileged": str(gid in privileged_ids).lower(),
                       "owner_id": owner_ids[0] if owner_ids else ""})
        members = client.pages(f"/groups/{quote(gid)}/members")
        seen_member_ids: set[str] = set()
        for member in members:
            mid = _require_id(member, "member")
            if mid in seen_member_ids:
                raise GraphExportError("Graph returned a duplicate group member; export aborted")
            seen_member_ids.add(mid)
            kind = member.get("@odata.type", "")
            if kind != "#microsoft.graph.user":
                non_users.append({"group_id": gid, "member_id": mid, "odata_type": kind or "unknown"})
                continue
            if mid not in users:
                person = client.get(f"/users/{quote(mid)}?$select=id,displayName,userType,accountEnabled,jobTitle")
                if _require_id(person, "user") != mid or not isinstance(person.get("accountEnabled"), bool):
                    raise GraphExportError("Graph returned incomplete user status; export aborted")
                if person.get("userType") not in ("Member", "Guest"):
                    raise GraphExportError("Graph returned incomplete user type; export aborted")
                users[mid] = {"user_id": mid, "display_name": person.get("displayName") or mid,
                              "user_type": person["userType"], "enabled": str(person["accountEnabled"]).lower(),
                              "job_role": person.get("jobTitle") or ""}
            # Graph member listing provides no historical access-grant timestamp.
            memberships.append({"group_id": gid, "user_id": mid, "granted_at": ""})
    manifest = {
        "schema": "graph-partial-v0.2", "source": "Microsoft Graph v1.0", "collected_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "group_ids": group_ids, "privileged_group_ids": sorted(privileged_ids),
        "records": {"users": len(users), "groups": len(groups), "direct_user_memberships": len(memberships),
                    "unassessed_non_user_memberships": len(non_users)},
        "group_owner_counts": owner_counts, "dynamic_group_ids": dynamic_groups,
        "coverage": "Selected groups only; direct members only; non-user members not assessed; owners first-listed for CSV compatibility.",
        "missing": ["original membership grant dates", "approval and campaign evidence", "SharePoint site permissions", "audit/SIEM events", "PIM and directory role assignments", "nested effective membership"],
        "warning": "This is a partial inventory, not a complete governance audit. Do not run all controls without independent evidence inputs.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=".graph-staging-", dir=output.parent))
    try:
        _write_csv(staged / "users.csv", ("user_id", "display_name", "user_type", "enabled", "job_role"), sorted(users.values(), key=lambda x: x["user_id"]))
        _write_csv(staged / "groups.csv", ("group_id", "name", "privileged", "owner_id"), groups)
        _write_csv(staged / "memberships.csv", ("group_id", "user_id", "granted_at"), memberships)
        _write_csv(staged / "non_user_members.csv", ("group_id", "member_id", "odata_type"), non_users)
        (staged / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        staged.rename(output)
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    return manifest
