from __future__ import annotations

import csv
import datetime as dt
import shutil
import tempfile
import unittest
from pathlib import Path

from governance_auditor.engine import analyze, load_snapshot, run_checks
from governance_auditor.reporting import _csv_safe, render_html, write_reports

HERE = Path(__file__).resolve().parents[1]
EXAMPLE = HERE / "examples" / "synthetic"
DATE = dt.date(2026, 11, 4)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.folder = Path(self.tempdir.name) / "input"
        shutil.copytree(EXAMPLE, self.folder)

    def rewrite(self, name: str, rows):
        p = self.folder / f"{name}.csv"
        with p.open(newline="", encoding="utf-8") as f:
            headers = csv.DictReader(f).fieldnames
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=headers)
            w.writeheader()
            w.writerows(rows)

    def test_expected_findings_and_valid_evidence_pairs(self):
        audit = analyze(self.folder, DATE)
        ids = [f.control_id for f in audit.findings]
        for control in ["PRV-001", "PRV-002", "PRV-003", "PRV-004", "SP-001", "SP-002", "SP-003", "REV-001", "AUD-001"]:
            self.assertIn(control, ids)
        self.assertEqual(audit.counts["correlated_evidence"], 2)
        self.assertEqual(audit.counts["excepted"], 1)
        self.assertTrue(any(f.control_id == "PRV-001" and f.subject == "u06" and f.status == "excepted" for f in audit.findings))
        self.assertFalse(any(f.control_id == "SP-001" and f.subject == "u08" for f in audit.findings))
        self.assertFalse(any(f.control_id == "REV-001" and f.subject == "CAM-004" for f in audit.findings))

    def test_expired_exception_does_not_suppress(self):
        self.rewrite("exceptions", [{"control_id": "PRV-001", "subject": "u06", "expires_on": "2026-10-01", "approved_by": "u07", "reason": "Expired"}])
        audit = analyze(self.folder, DATE)
        self.assertTrue(any(f.control_id == "PRV-001" and f.subject == "u06" and f.status == "open" for f in audit.findings))

    def test_late_approval_flagged(self):
        audit = analyze(self.folder, DATE)
        self.assertEqual([f.subject for f in audit.findings if f.control_id == "PRV-002"], ["u05"])

    def test_missing_input_is_rejected(self):
        (self.folder / "sites.csv").unlink()
        with self.assertRaisesRegex(ValueError, "Missing required file"):
            load_snapshot(self.folder)

    def test_malformed_membership_is_rejected(self):
        self.rewrite("memberships", [{"group_id": "bad", "user_id": "unknown", "granted_at": "2026-10-01"}])
        with self.assertRaisesRegex(ValueError, "unknown group/user"):
            analyze(self.folder, DATE)

    def test_bad_and_duplicate_approvals_rejected(self):
        approvals, _ = load_snapshot(self.folder)
        self.rewrite("approvals", approvals["approvals"] + [approvals["approvals"][0]])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            load_snapshot(self.folder)

    def test_html_escapes_untrusted_inputs(self):
        dataset, hashes = load_snapshot(self.folder)
        dataset["sites"][0]["name"] = '<img src=x onerror=alert(1)>'
        audit = run_checks(dataset, hashes, DATE)
        page = render_html(audit)
        self.assertNotIn('<img src=x onerror', page)
        self.assertIn('&lt;img src=x onerror', page)

    def test_report_outputs_and_checksums(self):
        audit = analyze(self.folder, DATE)
        paths = write_reports(audit, Path(self.tempdir.name) / "reports")
        self.assertTrue(all(p.is_file() for p in paths.values()))
        self.assertIn("EVT-001", paths["evidence"].read_text(encoding="utf-8"))

    def test_csv_formula_injection_is_neutralized(self):
        self.assertEqual(_csv_safe("=HYPERLINK(\"http://bad\")"), "'=HYPERLINK(\"http://bad\")")
        self.assertEqual(_csv_safe("@SUM(A1:A2)"), "'@SUM(A1:A2)")
        self.assertEqual(_csv_safe("harmless"), "harmless")

    def test_earlier_snapshot_not_overdue(self):
        audit = analyze(self.folder, dt.date(2026, 10, 15))
        self.assertFalse(any(f.control_id == "REV-001" for f in audit.findings))

if __name__ == "__main__":
    unittest.main()
