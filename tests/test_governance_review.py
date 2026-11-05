from __future__ import annotations
import csv
import datetime as dt
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from governance_auditor.governance_review import ReviewError, _change_id, initialize_review, export_review_package
from governance_auditor.__main__ import main

ROOT = Path(__file__).resolve().parents[1]
AS_OF = dt.datetime(2026,11,5,12,0,tzinfo=dt.timezone.utc)


class GovernanceReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)
        self.comparison=self.home/'comparison'
        shutil.copytree(ROOT/'examples'/'change_demo_output',self.comparison)
        self.plan=self.home/'plan'
        self.package=self.home/'package'
        initialize_review(self.comparison,self.plan)

    def rows(self):
        with (self.plan/'reviews.csv').open(encoding='utf-8',newline='') as fh:
            rd=csv.DictReader(fh)
            return rd.fieldnames,list(rd)

    def edit(self, mutator):
        fields,rows=self.rows()
        mutator(rows)
        with (self.plan/'reviews.csv').open('w',encoding='utf-8',newline='') as fh:
            wr=csv.DictWriter(fh,fieldnames=fields,lineterminator='\n')
            wr.writeheader();wr.writerows(rows)

    def good(self, row):
        row.update(disposition='acknowledged',reviewer='reviewer_alpha',reviewed_at_utc='2026-11-04T12:00:00Z',rationale='Synthetic review performed')

    def export(self):
        return export_review_package(self.comparison,self.plan,self.package,AS_OF)

    def test_template_has_stable_unique_ids_and_no_automatic_approval(self):
        _,rows=self.rows()
        self.assertEqual(len(rows),9)
        self.assertEqual(len(set(r['change_id'] for r in rows)),9)
        self.assertTrue(all(x['disposition']=='pending' and not x['reviewer'] for x in rows))
        self.assertTrue(all(x['change_id'].startswith('CHG-') for x in rows))

    def test_pending_generates_package_without_forged_review(self):
        manifest=self.export()
        self.assertEqual(manifest['changes'],9)
        self.assertEqual(manifest['review_flags']['awaiting_review'],9)
        self.assertEqual(manifest['tracked_actions'],0)
        self.assertEqual(manifest['coverage_warnings'],2)  # Non-comparable and partial selected-users coverage
        self.assertTrue((self.package/'dashboard.html').exists())
        with (self.package/'remediation_actions.csv').open(encoding='utf-8',newline='') as fh:
            self.assertEqual(len(list(csv.DictReader(fh))),0)
        self.assertIn('changes.csv',manifest['source_comparison_sha256'])
        self.assertIn('dashboard.html',manifest['output_sha256'])

    def test_record_review_and_action(self):
        def mutate(rows):
            self.good(rows[0]);self.good(rows[1])
            rows[1].update(disposition='remediate',action_owner='team_alpha',action_due_utc='2026-11-10T00:00:00Z',action_status='open')
        self.edit(mutate)
        result=self.export()
        self.assertEqual(result['tracked_actions'],1)
        self.assertEqual(result['review_flags']['reviewed_self_reported'],1)
        self.assertEqual(result['review_flags']['action_open'],1)
        with (self.package/'remediation_actions.csv').open(encoding='utf-8',newline='') as fh:
            self.assertEqual(len(list(csv.DictReader(fh))),1)

    def test_exception_requires_separate_approver_and_expiry(self):
        self.edit(lambda rows:(self.good(rows[0]),rows[0].update(disposition='exception',exception_expires_utc='2026-12-01T12:00:00Z',exception_approved_by='reviewer_alpha')))
        with self.assertRaisesRegex(ReviewError,'different'):self.export()
        self.assertFalse(self.package.exists())

    def test_expired_exception_remains_visible(self):
        self.edit(lambda rows:(self.good(rows[0]),rows[0].update(disposition='exception',exception_expires_utc='2026-11-04T20:00:00Z',exception_approved_by='approver_beta')))
        result=self.export()
        self.assertEqual(result['review_flags']['exception_expired'],1)

    def test_stale_change_source_rejected(self):
        with (self.comparison/'changes.csv').open('a',encoding='utf-8') as fh:fh.write('\n')
        with self.assertRaisesRegex(ReviewError,'stale|modified'):self.export()
        self.assertFalse(self.package.exists())

    def test_duplicate_or_missing_review_rejected(self):
        self.edit(lambda rows: rows.__setitem__(1,dict(rows[0])))
        with self.assertRaisesRegex(ReviewError,'duplicate'):self.export()
        self.assertFalse(self.package.exists())

    def test_closed_action_requires_evidence_reference(self):
        self.edit(lambda rows:(self.good(rows[0]),rows[0].update(disposition='remediate',action_owner='team_alpha',action_due_utc='2026-11-12T00:00:00Z',action_status='closed')))
        with self.assertRaisesRegex(ReviewError,'closure evidence'):self.export()

    def test_no_future_reviews(self):
        self.edit(lambda rows:(self.good(rows[0]),rows[0].update(reviewed_at_utc='2026-11-20T10:00:00Z')))
        with self.assertRaisesRegex(ReviewError,'future'):self.export()

    def test_pending_with_reviewer_fails(self):
        self.edit(lambda rows:rows[0].update(reviewer='not_yet'))
        with self.assertRaisesRegex(ReviewError,'Pending'):self.export()

    def test_csv_formula_and_html_injection_neutralized(self):
        self.edit(lambda rows:(self.good(rows[0]),rows[0].update(rationale='<img src=x onerror=alert(1)>',reviewer='=HYPERLINK("http://example.test")')))
        self.export()
        body=(self.package/'dashboard.html').read_text(encoding='utf-8')
        self.assertNotIn('<img src=x onerror',body)
        self.assertIn('&lt;img src=x onerror',body)
        with (self.package/'reviewed_changes.csv').open(encoding='utf-8') as fh:
            lines=fh.read()
        self.assertIn('"\'=HYPERLINK',lines)

    def test_reject_existing_output_without_change(self):
        self.package.mkdir()
        (self.package/'keep.txt').write_text('preserve')
        with self.assertRaisesRegex(ReviewError,'fresh'):self.export()
        self.assertEqual((self.package/'keep.txt').read_text(),'preserve')

    def test_missing_input_manifest_fails(self):
        (self.comparison/'manifest.json').unlink()
        with self.assertRaisesRegex(ReviewError,'JSON'):self.export()
        self.assertFalse(self.package.exists())

    def test_mismatched_review_source_rejected(self):
        doc=json.loads((self.plan/'source.json').read_text())
        doc['changes']=999
        (self.plan/'source.json').write_text(json.dumps(doc))
        with self.assertRaisesRegex(ReviewError,'stale'):self.export()

    def test_malformed_review_csv_fails(self):
        with (self.plan/'reviews.csv').open('a') as fh: fh.write('unknown,one\n')
        with self.assertRaisesRegex(ReviewError,'Malformed'):self.export()

    def test_cli_init_and_package(self):
        init=self.home/'cli_plan';pkg=self.home/'cli_pkg'
        self.assertEqual(main(['review-init','--comparison',str(self.comparison),'--output',str(init)]),0)
        self.assertEqual(main(['review-package','--comparison',str(self.comparison),'--plan',str(init),'--output',str(pkg),'--as-of','2026-11-05T12:00:00Z']),0)
        self.assertTrue((pkg/'package_manifest.json').is_file())

    def test_review_init_reject_output_within_comparison(self):
        with self.assertRaisesRegex(ReviewError,'outside'):initialize_review(self.comparison,self.comparison/'inside')

    def test_reject_naive_as_of(self):
        with self.assertRaisesRegex(ReviewError,'offset'):export_review_package(self.comparison,self.plan,self.package,dt.datetime(2026,11,5))

    def test_invalid_action_status(self):
        self.edit(lambda rows:(self.good(rows[0]),rows[0].update(disposition='investigate',action_owner='team_alpha',action_due_utc='2026-11-10T00:00:00Z',action_status='definitely_done')))
        with self.assertRaisesRegex(ReviewError,'Action owner'):self.export()

    def test_change_id_deterministic(self):
        with (self.comparison/'changes.csv').open(encoding='utf-8',newline='') as fh:
            r=list(csv.DictReader(fh))[0]
        self.assertEqual(_change_id(r),_change_id(dict(reversed(list(r.items())))))

if __name__=='__main__':unittest.main()