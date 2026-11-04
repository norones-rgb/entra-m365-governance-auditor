"""Mock Graph tests: no network, tenant, or credentials required."""
from __future__ import annotations
import csv
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from governance_auditor.graph_export import GraphClient, GraphExportError
from governance_auditor.review_export import export_reviews, _parse_date_time

D1 = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
D2 = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
I1 = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
I2 = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'
U1 = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'
NOW = dt.datetime(2026, 11, 4, 17, 0, tzinfo=dt.timezone.utc)


def fixtures():
    return {
        f'/identityGovernance/accessReviews/definitions/{D1}': {'id': D1, 'displayName': 'Quarterly Access Review'},
        f'/identityGovernance/accessReviews/definitions/{D1}/instances': {'value': [
            {'id': I1, 'status': 'InProgress', 'startDateTime': '2026-10-01T00:00:00Z', 'endDateTime': '2026-11-01T00:00:00Z'},
            {'id': I2, 'status': 'Completed', 'startDateTime': '2026-08-01T00:00:00Z', 'endDateTime': '2026-09-01T00:00:00Z'}]},
        f'/identityGovernance/accessReviews/definitions/{D1}/instances/{I1}/decisions': {'value': [
            {'decision': 'Approve', 'principal': {'id': U1}}, {'decision': 'NotReviewed', 'principal': {'id': U1}},
            {'decision': 'Deny', 'principal': {'id': U1}}]},
        f'/identityGovernance/accessReviews/definitions/{D1}/instances/{I2}/decisions': {'value': [{'decision': 'Approve'}]},
    }


def fake_client(payloads):
    def request(url, token):
        if token != 'fake-token':
            raise AssertionError('Unexpected token')
        path = url.removeprefix('https://graph.microsoft.com/v1.0')
        return payloads[path]
    return GraphClient('fake-token', request)


class ReviewExportTests(unittest.TestCase):
    def test_review_counts_and_no_participant_details(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'reviews'
            result = export_reviews(fake_client(fixtures()), [D1], output, NOW)
            self.assertEqual(result['instance_count'], 2)
            self.assertEqual(result['overdue_indicators'], 1)
            with (output / 'review_instances.csv').open(newline='', encoding='utf8') as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]['decision_total'], '3')
            self.assertEqual(rows[0]['not_reviewed'], '1')
            self.assertEqual(rows[0]['approve'], '1')
            self.assertEqual(rows[0]['deny'], '1')
            self.assertEqual(rows[0]['overdue'], 'true')
            self.assertEqual(rows[1]['overdue'], 'false')
            for name in ('review_instances.csv', 'dashboard.html', 'manifest.json'):
                self.assertNotIn(U1, (output / name).read_text(encoding='utf8'))
            with self.assertRaisesRegex(GraphExportError, 'already exists'):
                export_reviews(fake_client(fixtures()), [D1], output, NOW)

    def test_rejects_duplicate_or_invalid_id(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'reviews'
            with self.assertRaisesRegex(GraphExportError, 'unique'):
                export_reviews(fake_client(fixtures()), [D1, D1], out, NOW)
            with self.assertRaisesRegex(GraphExportError, 'GUID'):
                export_reviews(fake_client(fixtures()), ['../anything'], out, NOW)
            self.assertFalse(out.exists())

    def test_unexpected_definition_does_not_write_output(self):
        data = fixtures()
        data[f'/identityGovernance/accessReviews/definitions/{D1}']['id'] = D2
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'reviews'
            with self.assertRaisesRegex(GraphExportError, 'different'):
                export_reviews(fake_client(data), [D1], out, NOW)
            self.assertFalse(out.exists())

    def test_missing_due_date_is_unknown_not_overdue(self):
        data = fixtures()
        data[f'/identityGovernance/accessReviews/definitions/{D1}/instances']['value'][0]['endDateTime'] = None
        with tempfile.TemporaryDirectory() as temp:
            result = export_reviews(fake_client(data), [D1], Path(temp) / 'reviews', NOW)
            self.assertEqual(result['overdue_indicators'], 0)

    def test_invalid_datetime_and_naive_as_of_rejected(self):
        with self.assertRaisesRegex(GraphExportError, 'timezone'):
            _parse_date_time('2026-11-04T12:00:00', 'when')
        with tempfile.TemporaryDirectory() as temp:
            data = fixtures()
            data[f'/identityGovernance/accessReviews/definitions/{D1}/instances']['value'][0]['endDateTime'] = 'not-a-date'
            dest = Path(temp) / 'out'
            with self.assertRaisesRegex(GraphExportError, 'ISO datetime'):
                export_reviews(fake_client(data), [D1], dest, NOW)
            self.assertFalse(dest.exists())
        with self.assertRaisesRegex(GraphExportError, 'timezone'):
            export_reviews(fake_client(fixtures()), [D1], Path(temp) / 'bad', dt.datetime(2026, 11, 4))

    def test_html_escaping_and_csv_formula_protection(self):
        data = fixtures()
        data[f'/identityGovernance/accessReviews/definitions/{D1}']['displayName'] = '=<img src=x onerror=alert(1)>'
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'results'
            export_reviews(fake_client(data), [D1], output, NOW)
            page = (output / 'dashboard.html').read_text(encoding='utf8')
            self.assertNotIn('<img src=x', page)
            self.assertIn('&lt;img src=x', page)
            with (output / 'review_instances.csv').open(newline='', encoding='utf8') as f:
                rows = list(csv.DictReader(f))
            self.assertTrue(rows[0]['definition_name'].startswith("'="))

    def test_pagination_works_for_selected_review_instances(self):
        data = fixtures()
        path = f'/identityGovernance/accessReviews/definitions/{D1}/instances'
        data[path] = {'value': [data[path]['value'][0]], '@odata.nextLink': f'https://graph.microsoft.com/v1.0{path}?$skiptoken=a'}
        data[path+'?$skiptoken=a'] = {'value': [{'id': I2, 'status': 'Completed'}]}
        with tempfile.TemporaryDirectory() as temp:
            result = export_reviews(fake_client(data), [D1], Path(temp) / 'results', NOW)
            self.assertEqual(result['instance_count'], 2)

    def test_sp_script_is_present_and_no_mutation_cmdlets(self):
        script = (Path(__file__).resolve().parents[1] / 'sharepoint' / 'Export-SitePermissions.ps1').read_text(encoding='utf8')
        for part in ('Get-PnPGroupMember', 'Get-PnPSiteCollectionAdmin', 'Get-PnPProperty', 'Connect-PnPOnline'):
            self.assertIn(part, script)
        for forbidden in ('Set-PnP', 'Add-PnP', 'Remove-PnP', 'Grant-PnP', 'Revoke-PnP'):
            self.assertNotIn(forbidden, script)


if __name__ == '__main__':
    unittest.main()
