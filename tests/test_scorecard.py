"""Network-free validation of v0.7 documented-workflow scorecard."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from governance_auditor.governance_review import ReviewError
from governance_auditor.scorecard import create_scorecard

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "examples/governance_demo_output"
COMPARISON = ROOT / "examples/change_demo_output"
DATE = dt.datetime(2026, 11, 15, 12, 0, tzinfo=dt.timezone.utc)


class ScorecardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.package = self.root / "package"
        shutil.copytree(PACKAGE, self.package)
        self.output = self.root / "scorecard"

    def generate(self, as_of=DATE, **kwargs):
        return create_scorecard(self.package, self.output, as_of, **kwargs)

    def rewrite(self, name: str, rows: list[dict]):
        file = self.package / name
        with file.open(newline="", encoding="utf-8") as f:
            fields = csv.DictReader(f).fieldnames
        with file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        self.rehash(name)

    def rehash(self, name: str):
        m = self.package / "package_manifest.json"
        manifest = json.loads(m.read_text(encoding="utf-8"))
        manifest["output_sha256"][name] = hashlib.sha256((self.package/name).read_bytes()).hexdigest()
        m.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")

    def test_expected_metrics_are_not_a_security_grade(self):
        score = self.generate()
        self.assertEqual(score["readiness"], "attention_required")
        self.assertEqual(score["counts"]["overdue_actions"], 2)
        self.assertEqual(score["counts"]["pending_reviews"], 4)
        metrics = {x["metric"]:x for x in score["metrics"]}
        self.assertEqual(metrics["documented_review_rate"]["percent"],55.6)
        self.assertEqual(metrics["comparable_collection_scope"]["percent"],50.0)
        self.assertEqual(metrics["open_action_timeliness"]["percent"],0.0)
        self.assertIsNone(metrics["closed_action_reference"]["percent"])
        self.assertNotIn("overall_security_score",score)

    def test_output_artifacts_and_integrity_hashes(self):
        self.generate()
        manifest = json.loads((self.output/"manifest.json").read_text())
        self.assertEqual(manifest["schema"],"offline-governance-scorecard-v0.7")
        for file,digest in manifest["output_sha256"].items():
            self.assertEqual(digest,hashlib.sha256((self.output/file).read_bytes()).hexdigest())
        self.assertEqual(set(manifest["output_sha256"]),{"dashboard.html","scorecard.json","scorecard.csv","action_queue.csv"})

    def test_optional_source_hash_verification(self):
        score = self.generate(comparison=COMPARISON,plan=self.package)
        self.assertEqual(score["source_validation"],{"comparison":"hashes_match","review_plan":"hashes_match"})

    def test_wrong_comparison_is_rejected(self):
        wrong = self.root/"wrong"
        shutil.copytree(COMPARISON,wrong)
        with (wrong/"changes.csv").open("a",encoding="utf-8") as f:f.write("\n")
        with self.assertRaisesRegex(ReviewError,"checksum mismatch"):
            self.generate(comparison=wrong)
        self.assertFalse(self.output.exists())

    def test_wrong_plan_is_rejected(self):
        other=self.root/"otherplan"
        other.mkdir()
        for name in ("reviews.csv","source.json"):
            shutil.copy(self.package/name,other/name)
        with (other/"reviews.csv").open("a",encoding="utf-8") as f:f.write("\n")
        with self.assertRaisesRegex(ReviewError,"checksum mismatch"):
            self.generate(plan=other)

    def test_package_checksum_change_blocks_output(self):
        with (self.package/"coverage.csv").open("a",encoding="utf-8") as f:f.write("\n")
        with self.assertRaisesRegex(ReviewError,"checksum mismatch"):
            self.generate()
        self.assertFalse(self.output.exists())

    def test_unexpected_manifest_digest_keys_are_rejected(self):
        path = self.package/"package_manifest.json"
        data=json.loads(path.read_text())
        data["output_sha256"]["../../evil"]="0"*64
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ReviewError,"digest list"):
            self.generate()

    def test_duplicate_review_id_rejected_even_if_rehashed(self):
        path=self.package/"reviewed_changes.csv"
        with path.open(newline="",encoding="utf-8") as f:rows=list(csv.DictReader(f))
        rows[1]["change_id"]=rows[0]["change_id"]
        self.rewrite("reviewed_changes.csv",rows)
        with self.assertRaisesRegex(ReviewError,"duplicate review change"):
            self.generate()

    def test_disposition_and_status_mismatch_rejected_even_if_rehashed(self):
        path=self.package/"reviewed_changes.csv"
        with path.open(newline="",encoding="utf-8") as f:rows=list(csv.DictReader(f))
        rows[0]["review_flag"]="awaiting_review"
        self.rewrite("reviewed_changes.csv",rows)
        with self.assertRaisesRegex(ReviewError,"Review flag contradicts"):
            self.generate()

    def test_review_summary_mismatch_rejected_even_if_rehashed(self):
        m=self.package/"package_manifest.json"
        data=json.loads(m.read_text())
        data["review_flags"]["awaiting_review"]=999
        m.write_text(json.dumps(data))
        with self.assertRaisesRegex(ReviewError,"flag totals"):
            self.generate()

    def test_action_record_mismatch_rejected_even_if_rehashed(self):
        p=self.package/"remediation_actions.csv"
        with p.open(newline="",encoding="utf-8") as f:rows=list(csv.DictReader(f))
        rows[0]["action_owner"]="not_the_actual_owner"
        self.rewrite("remediation_actions.csv",rows)
        with self.assertRaisesRegex(ReviewError,"does not match"):
            self.generate()

    def test_timezone_aware_asof_required(self):
        with self.assertRaisesRegex(ReviewError,"timezone-aware"):
            self.generate(as_of=dt.datetime(2026,11,15,12,0))

    def test_asof_cannot_precede_package(self):
        with self.assertRaisesRegex(ReviewError,"precedes"):
            self.generate(as_of=dt.datetime(2026,11,4,12,0,tzinfo=dt.timezone.utc))

    def test_expired_exception_recomputed_from_current_time(self):
        score=self.generate(as_of=dt.datetime(2027,1,2,tzinfo=dt.timezone.utc))
        self.assertEqual(score["counts"]["expired_exceptions"],1)
        self.assertEqual(next(m for m in score["metrics"] if m["metric"]=="exception_currency")["percent"],0.0)

    def test_open_action_timeliness_recomputed(self):
        score=self.generate(as_of=dt.datetime(2026,11,5,12,tzinfo=dt.timezone.utc))
        self.assertEqual(score["counts"]["overdue_actions"],0)
        self.assertEqual(next(m for m in score["metrics"] if m["metric"]=="open_action_timeliness")["percent"],100.0)

    def test_existing_output_rejected(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ReviewError,"fresh"):
            self.generate()

    def test_output_nested_inside_package_rejected(self):
        with self.assertRaisesRegex(ReviewError,"outside all input"):
            create_scorecard(self.package,self.package/"nested",DATE)

    def test_report_escapes_html_and_csv_formula_values(self):
        p=self.package/"remediation_actions.csv"
        with p.open(newline="",encoding="utf-8") as f:rows=list(csv.DictReader(f))
        rows[0]["action_owner"]='=<script>alert(1)</script>'
        self.rewrite("remediation_actions.csv",rows)
        # Matching review record must also be changed to satisfy coherence checks.
        p=self.package/"reviewed_changes.csv"
        with p.open(newline="",encoding="utf-8") as f:reviewed=list(csv.DictReader(f))
        match=next(x for x in reviewed if x["change_id"]==rows[0]["change_id"])
        match["action_owner"]=rows[0]["action_owner"]
        self.rewrite("reviewed_changes.csv",reviewed)
        self.generate()
        html=(self.output/"dashboard.html").read_text()
        self.assertNotIn('<script>alert(1)</script>',html)
        self.assertIn('&lt;script&gt;',html)
        csv_data=(self.output/"action_queue.csv").read_text()
        self.assertIn("'=",csv_data)

    def test_no_source_confidence_when_optional_files_absent(self):
        score=self.generate()
        self.assertEqual(score["source_validation"],{"comparison":"not_supplied","review_plan":"not_supplied"})


if __name__ == '__main__':
    unittest.main()