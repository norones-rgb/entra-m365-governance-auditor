"""Network-free reconciliation behavior and safety tests."""
from __future__ import annotations
import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from governance_auditor.reconcile import (ReconcileError, reconcile, _identity_from_login,
                                           _normal_alias)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/reconciliation_synthetic"


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(EXAMPLES / "graph", self.root / "graph")
        shutil.copytree(EXAMPLES / "sharepoint", self.root / "sharepoint")
        self.output = self.root / "result"

    def rows(self, source="sharepoint_group_members"):
        path = self.root / "sharepoint" / (source + ".csv")
        with path.open(newline="", encoding="utf8") as f:
            return list(csv.DictReader(f))

    def write_rows(self, rows, source="sharepoint_group_members"):
        path = self.root / "sharepoint" / (source + ".csv")
        with path.open(newline="", encoding="utf8") as f:
            fields = csv.DictReader(f).fieldnames
        with path.open("w", newline="", encoding="utf8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    def result_rows(self):
        reconcile(self.root / "graph", self.root / "sharepoint", self.output)
        with (self.output / "identity_matches.csv").open(newline="", encoding="utf8") as f:
            return list(csv.DictReader(f))

    def test_expected_resolutions_and_disabled_account_indicator(self):
        rows = self.result_rows()
        self.assertEqual(len(rows), 9)
        from collections import Counter
        self.assertEqual(Counter(x["resolution"] for x in rows),
                         Counter({"matched": 5, "ambiguous": 1, "out_of_scope": 2, "unresolved": 1}))
        self.assertEqual(sum(x["review_indicator"] != "" for x in rows), 1)
        self.assertEqual(rows[1]["directory_kind"], "user")
        self.assertEqual(rows[1]["account_enabled"], "false")

    def test_guid_group_match_does_not_imply_nested_effective_access(self):
        rows = self.result_rows()
        groups = [x for x in rows if x["directory_kind"] == "group"]
        self.assertEqual(len(groups), 2)
        self.assertTrue(all(not x["review_indicator"] for x in groups))
        self.assertIn("NOT calculated effective permissions", (self.output / "dashboard.html").read_text())

    def test_ambiguous_alias_never_resolves_to_arbitrary_user(self):
        rows = self.result_rows()
        row = [x for x in rows if "shared@example.test" in x["principal_login"]][0]
        self.assertEqual(row["resolution"], "ambiguous")
        self.assertEqual(row["directory_id"], "")

    def test_claim_format_is_strict(self):
        self.assertEqual(_identity_from_login("i:0#.f|membership|USER@EXAMPLE.TEST"), ("alias", "user@example.test"))
        self.assertEqual(_identity_from_login("prefix-11111111-1111-4111-8111-111111111111"), (None, None))
        self.assertEqual(_normal_alias("abc@no"), None)

    def test_source_manifest_missing_prevents_output(self):
        (self.root / "sharepoint" / "manifest.json").unlink()
        with self.assertRaisesRegex(ReconcileError, "manifest"):
            reconcile(self.root / "graph", self.root / "sharepoint", self.output)
        self.assertFalse(self.output.exists())

    def test_site_mismatch_prevents_output(self):
        rows = self.rows()
        rows[0]["site_url"] = "https://unrelated.sharepoint.com/sites/other"
        self.write_rows(rows)
        with self.assertRaisesRegex(ReconcileError, "inconsistent"):
            reconcile(self.root / "graph", self.root / "sharepoint", self.output)
        self.assertFalse(self.output.exists())

    def test_duplicate_graph_user_rejected(self):
        p = self.root / "graph" / "users.csv"
        with p.open("a", encoding="utf8") as h:
            h.write("11111111-1111-4111-8111-111111111111,Clone,Member,true,Analyst\n")
        with self.assertRaisesRegex(ReconcileError, "Duplicate"):
            reconcile(self.root / "graph", self.root / "sharepoint", self.output)

    def test_csv_formula_and_html_injection_protection(self):
        rows = self.rows()
        rows[5]["principal_login"] = '=HYPERLINK("<img src=x onerror=alert(1)>")'
        rows[5]["principal_email"] = 'invalid'
        self.write_rows(rows)
        values = self.result_rows()
        self.assertTrue(values[5]["principal_login"].startswith("'="))
        page = (self.output / "dashboard.html").read_text(encoding="utf8")
        self.assertNotIn('<img src=x onerror', page)
        self.assertIn('&lt;', page)

    def test_graph_older_alias_free_snapshot_remains_partial(self):
        (self.root / "graph" / "identity_aliases.csv").unlink()
        rows = self.result_rows()
        self.assertEqual(sum(x["directory_kind"] == "user" for x in rows), 0)
        self.assertEqual(sum(x["directory_kind"] == "group" for x in rows), 2)

    def test_existing_output_and_input_output_overlap_rejected(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ReconcileError, "fresh"):
            reconcile(self.root / "graph", self.root / "sharepoint", self.output)
        self.output.rmdir()
        with self.assertRaisesRegex(ReconcileError, "fresh"):
            reconcile(self.root / "graph", self.root / "sharepoint", self.root / "graph" / "out")

    def test_timestamp_gap_is_a_warning_not_a_finding(self):
        p = self.root / "sharepoint" / "manifest.json"
        data = json.loads(p.read_text())
        data["collected_at_utc"] = "2026-10-01T12:00:00+00:00"
        p.write_text(json.dumps(data))
        self.result_rows()
        manifest = json.loads((self.output / "manifest.json").read_text())
        self.assertIs(manifest["source_time_gap_gt_72_hours"], True)
        self.assertEqual(manifest["disabled_account_review_indicators"], 1)

    def test_invalid_alias_is_rejected(self):
        p = self.root / "graph" / "identity_aliases.csv"
        p.write_text(p.read_text().replace("alex@example.test", "bad-alias"))
        with self.assertRaisesRegex(ReconcileError, "complete email-shaped"):
            reconcile(self.root / "graph", self.root / "sharepoint", self.output)

if __name__ == "__main__":
    unittest.main()