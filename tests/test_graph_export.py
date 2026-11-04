"""Network-free contract tests for the optional read-only Graph connector."""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError

from governance_auditor.engine import analyze
from governance_auditor.graph_export import GraphClient, GraphExportError, export_snapshot, valid_guid

G1 = "11111111-1111-4111-8111-111111111111"
G2 = "22222222-2222-4222-8222-222222222222"
U1 = "33333333-3333-4333-8333-333333333333"
U2 = "44444444-4444-4444-8444-444444444444"
DEVICE = "55555555-5555-4555-8555-555555555555"


def fake_api():
    return {
        f"/groups/{G1}?$select=id,displayName,groupTypes": {"id": G1, "displayName": "Sample privileged group", "groupTypes": []},
        f"/groups/{G1}/owners": {"value": [{"id": U2}]},
        f"/groups/{G1}/members": {"value": [{"id": U1, "@odata.type": "#microsoft.graph.user"}],
                                   "@odata.nextLink": f"https://graph.microsoft.com/v1.0/groups/{G1}/members?$skiptoken=next"},
        f"/groups/{G1}/members?$skiptoken=next": {"value": [{"id": DEVICE, "@odata.type": "#microsoft.graph.device"}]},
        f"/users/{U1}?$select=id,displayName,userType,accountEnabled,jobTitle": {
            "id": U1, "displayName": "Demo Operator", "userType": "Member", "accountEnabled": False,
            "jobTitle": "Support Engineer"},
    }


class GraphTests(unittest.TestCase):
    def test_pagination_and_safe_partial_export(self):
        fixtures = fake_api()
        calls = []
        def request(url, token):
            self.assertEqual(token, "example-token")
            calls.append(url)
            return fixtures[url.removeprefix("https://graph.microsoft.com/v1.0")]
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "export"
            manifest = export_snapshot(GraphClient("example-token", request), [G1], {G1}, dest)
            self.assertEqual(manifest["records"]["direct_user_memberships"], 1)
            self.assertEqual(manifest["records"]["unassessed_non_user_memberships"], 1)
            self.assertIn("original membership grant dates", manifest["missing"])
            with (dest / "memberships.csv").open(newline="", encoding="utf8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows, [{"group_id": G1, "user_id": U1, "granted_at": ""}])
            with (dest / "users.csv").open(newline="", encoding="utf8") as handle:
                self.assertEqual(list(csv.DictReader(handle))[0]["enabled"], "false")
            self.assertTrue((dest / "non_user_members.csv").is_file())
            self.assertFalse((dest / "approvals.csv").exists())
            self.assertTrue(any("skiptoken=next" in url for url in calls))
            with self.assertRaisesRegex(GraphExportError, "already exists"):
                export_snapshot(GraphClient("example-token", request), [G1], {G1}, dest)

    def test_rejects_external_pagination_host(self):
        client = GraphClient("token", lambda _u, _t: {"value": [], "@odata.nextLink": "https://evil.example/steal"})
        with self.assertRaisesRegex(GraphExportError, "unexpected Graph"):
            client.pages(f"/groups/{G1}/members")

    def test_rejects_pagination_loop(self):
        url = f"https://graph.microsoft.com/v1.0/groups/{G1}/members"
        client = GraphClient("token", lambda _u, _t: {"value": [], "@odata.nextLink": url})
        with self.assertRaisesRegex(GraphExportError, "pagination loop"):
            client.pages(f"/groups/{G1}/members")

    def test_retries_throttling_without_exposing_token(self):
        calls, delays = [], []
        def throttled(url, token):
            calls.append(url)
            if len(calls) == 1:
                raise HTTPError(url, 429, "Throttled", {"Retry-After": "2"}, io.BytesIO(b""))
            return {"value": []}
        client = GraphClient("private-token", throttled, delays.append)
        self.assertEqual(client.pages(f"/groups/{G1}/members"), [])
        self.assertEqual(delays, [2.0])
        self.assertEqual(len(calls), 2)

    def test_incomplete_user_status_does_not_write_partial_output(self):
        fixtures = fake_api()
        del fixtures[f"/users/{U1}?$select=id,displayName,userType,accountEnabled,jobTitle"]["accountEnabled"]
        client = GraphClient("token", lambda url, _t: fixtures[url.removeprefix("https://graph.microsoft.com/v1.0")])
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "export"
            with self.assertRaisesRegex(GraphExportError, "incomplete user status"):
                export_snapshot(client, [G1], {G1}, dest)
            self.assertFalse(dest.exists())

    def test_unsafe_configuration_rejected(self):
        self.assertEqual(valid_guid(G1, "group"), G1)
        with self.assertRaises(GraphExportError):
            valid_guid("../something", "group")
        with tempfile.TemporaryDirectory() as temp:
            client = GraphClient("token", lambda _u, _t: {})
            with self.assertRaisesRegex(GraphExportError, "privileged group"):
                export_snapshot(client, [G1], {G2}, Path(temp) / "x")

    def test_unknown_grant_date_skips_late_approval_control(self):
        example = Path(__file__).resolve().parents[1] / "examples" / "synthetic"
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for file in example.glob("*.csv"):
                (folder / file.name).write_bytes(file.read_bytes())
            memberships = (folder / "memberships.csv").read_text(encoding="utf8")
            (folder / "memberships.csv").write_text(memberships.replace("G_NETOPS,u05,2026-09-07", "G_NETOPS,u05,"), encoding="utf8")
            audit = analyze(folder, dt.date(2026, 11, 4))
            self.assertFalse(any(f.control_id == "PRV-002" and f.subject == "u05" for f in audit.findings))
            self.assertGreater(len(audit.findings), 0)


if __name__ == "__main__":
    unittest.main()