from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from governance_auditor.snapshot_diff import ComparisonError, compare_snapshots, _safe_csv, _html

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples' / 'change_synthetic'


class SnapshotComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / 'data'
        shutil.copytree(EXAMPLES, self.data)
        self.before_graph = self.data / 'before' / 'graph'
        self.after_graph = self.data / 'after' / 'graph'
        self.before_site = self.data / 'before' / 'sharepoint'
        self.after_site = self.data / 'after' / 'sharepoint'
        self.out = self.root / 'reports' / 'diff'

    def run_compare(self, sites=True):
        return compare_snapshots(self.before_graph, self.after_graph, self.out,
                                 self.before_site if sites else None,
                                 self.after_site if sites else None)

    def read_rows(self, filename):
        with (self.out / filename).open(newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))

    def edit_manifest(self, folder, **values):
        p = folder / 'manifest.json'
        doc = json.loads(p.read_text(encoding='utf-8'))
        doc.update(values)
        p.write_text(json.dumps(doc), encoding='utf-8')

    def change_rows(self, folder, filename, change):
        p = folder / filename
        with p.open(newline='', encoding='utf-8') as handle:
            reader = csv.DictReader(handle)
            headers, rows = reader.fieldnames, list(reader)
        change(rows)
        with p.open('w', newline='', encoding='utf-8') as handle:
            w = csv.DictWriter(handle, headers, lineterminator='\n')
            w.writeheader()
            w.writerows(rows)

    def test_demo_reports_expected_comparable_changes(self):
        summary = self.run_compare()
        self.assertEqual(summary['schema'], 'selected-access-change-v0.5')
        self.assertEqual(summary['changes'], 9)
        self.assertEqual(summary['non_comparable_scopes'], 1)
        changes = self.read_rows('changes.csv')
        self.assertEqual(len(changes), 9)
        self.assertIn('account_status', [x['category'] for x in changes])
        self.assertEqual(sum(x['category'] == 'direct_user_membership' for x in changes), 2)
        self.assertEqual(sum(x['category'] == 'group_roster' for x in changes), 2)
        self.assertIn('https://demo.sharepoint.com/sites/example', (self.out/'dashboard.html').read_text())
        self.assertTrue(summary['source_sha256']['before_graph']['users.csv'])

    def test_new_group_scope_does_not_count_as_new_memberships(self):
        self.run_compare(sites=False)
        changes = self.read_rows('changes.csv')
        self.assertFalse(any(x['resource'] == '66666666-6666-4666-8666-666666666666' for x in changes))
        coverage = self.read_rows('coverage.csv')
        newly_selected = [x for x in coverage if x['scope'].startswith('66666666')][0]
        self.assertEqual(newly_selected['comparable'], 'no')
        self.assertEqual(newly_selected['before'], 'not selected')

    def test_dropped_group_scope_does_not_count_as_removal(self):
        # Swap order, and timestamps, to model a previously selected group falling out of collection scope.
        self.edit_manifest(self.before_graph, collected_at_utc='2026-12-01T12:00:00+00:00')
        self.edit_manifest(self.after_graph, collected_at_utc='2026-10-01T12:00:00+00:00')
        summary = compare_snapshots(self.after_graph, self.before_graph, self.out)
        self.assertEqual(summary['non_comparable_scopes'], 1)
        self.assertFalse(any(x['resource'] == '66666666-6666-4666-8666-666666666666' for x in self.read_rows('changes.csv')))

    def test_missing_manifest_rejected_without_partial_output(self):
        (self.before_graph / 'manifest.json').unlink()
        with self.assertRaisesRegex(ComparisonError, 'manifest'):
            self.run_compare()
        self.assertFalse(self.out.exists())

    def test_reversed_collection_time_rejected(self):
        self.edit_manifest(self.after_graph, collected_at_utc='2026-09-01T12:00:00Z')
        with self.assertRaisesRegex(ComparisonError, 'later'):
            self.run_compare()
        self.assertFalse(self.out.exists())

    def test_optional_sharepoint_requires_pair(self):
        with self.assertRaisesRegex(ComparisonError, 'both'):
            compare_snapshots(self.before_graph, self.after_graph, self.out, self.before_site, None)
        self.assertFalse(self.out.exists())

    def test_different_site_scope_suppresses_site_change_reporting(self):
        changed_site = 'https://demo.sharepoint.com/sites/another'
        self.edit_manifest(self.after_site, site_url=changed_site)
        for fn in ('sharepoint_group_members.csv', 'site_collection_admins.csv', 'root_web_role_assignments.csv'):
            self.change_rows(self.after_site, fn, lambda rows: [r.__setitem__('site_url', changed_site) for r in rows])
        summary = self.run_compare()
        self.assertEqual(summary['non_comparable_scopes'], 2)
        self.assertFalse(any(x['system'] == 'SharePoint' for x in self.read_rows('changes.csv')))

    def test_mismatched_graph_scope_manifest_rejected(self):
        self.edit_manifest(self.after_graph, group_ids=['55555555-5555-4555-8555-555555555555'])
        with self.assertRaisesRegex(ComparisonError, 'scope'):
            self.run_compare()
        self.assertFalse(self.out.exists())

    def test_duplicate_graph_membership_rejected(self):
        self.change_rows(self.after_graph, 'memberships.csv', lambda rows: rows.append(dict(rows[0])))
        with self.assertRaisesRegex(ComparisonError, 'duplicate'):
            self.run_compare()

    def test_malformed_user_status_rejected(self):
        self.change_rows(self.after_graph, 'users.csv', lambda rows: rows[0].__setitem__('enabled', 'unknown'))
        with self.assertRaisesRegex(ComparisonError, 'status'):
            self.run_compare()

    def test_csv_formula_injection_safe(self):
        self.assertEqual(_safe_csv('=HYPERLINK("example")'), "'=HYPERLINK(\"example\")")
        self.assertEqual(_safe_csv('   @formula'), "'   @formula")
        self.assertEqual(_safe_csv('normal'), 'normal')

    def test_html_escapes_input(self):
        page = _html([{'system':'<img src=x onerror=alert(1)>','category':'test','change':'added'}], [])
        self.assertNotIn('<img src=x onerror', page)
        self.assertIn('&lt;img src=x onerror', page)

    def test_existing_output_rejected_no_mutation(self):
        self.out.mkdir(parents=True)
        (self.out / 'important.txt').write_text('keep',encoding='utf-8')
        with self.assertRaisesRegex(ComparisonError, 'fresh'):
            self.run_compare()
        self.assertEqual((self.out / 'important.txt').read_text(), 'keep')

    def test_sharepoint_site_record_mismatch_rejected(self):
        self.change_rows(self.after_site,'site_collection_admins.csv',lambda rows: rows[0].__setitem__('site_url','https://other.sharepoint.com/sites/wrong'))
        with self.assertRaisesRegex(ComparisonError,'different site'):
            self.run_compare()

    def test_identical_graph_snapshots_only_status_coverage(self):
        # The same exported rows, but an independent, later collection time.
        for name in ('groups.csv','users.csv','memberships.csv','non_user_members.csv'):
            shutil.copyfile(self.before_graph/name,self.after_graph/name)
        self.edit_manifest(self.after_graph, group_ids=['55555555-5555-4555-8555-555555555555'])
        summary = self.run_compare(sites=False)
        self.assertEqual(summary['changes'], 0)
        self.assertEqual(summary['non_comparable_scopes'],0)


if __name__ == '__main__':
    unittest.main()
