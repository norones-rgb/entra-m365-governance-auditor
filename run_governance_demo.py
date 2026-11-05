"""Reproducible, synthetic workflow: drift -> review sheet -> evidence package."""
from __future__ import annotations
import csv
import datetime as dt
import json
import shutil
from pathlib import Path

from governance_auditor.governance_review import initialize_review, export_review_package

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'examples' / 'change_demo_output'
DEST = ROOT / 'reports' / 'governance-demo'
PLAN = DEST / 'plan'
PACKAGE = DEST / 'package'
AS_OF = dt.datetime(2026, 11, 5, 12, 0, tzinfo=dt.timezone.utc)


def run() -> dict:
    if DEST.exists():
        shutil.rmtree(DEST) # Only the known generated demo directory; never inputs
    initialize_review(BASE, PLAN)
    with (PLAN/'reviews.csv').open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    decisions = [
        {'disposition':'acknowledged','reviewer':'reviewer_alpha','reviewed_at_utc':'2026-11-04T15:00:00Z','rationale':'Status change reviewed; investigation scoped separately.'},
        {'disposition':'investigate','reviewer':'reviewer_beta','reviewed_at_utc':'2026-11-04T15:02:00Z','rationale':'Unexpected service principal membership requires validation.',
         'action_owner':'identity_ops','action_due_utc':'2026-11-12T00:00:00Z','action_status':'open'},
        {'disposition':'remediate','reviewer':'reviewer_beta','reviewed_at_utc':'2026-11-04T15:05:00Z','rationale':'Confirm removal evidence in authoritative directory.',
         'action_owner':'identity_ops','action_due_utc':'2026-11-06T00:00:00Z','action_status':'in_progress'},
        {'disposition':'exception','reviewer':'reviewer_alpha','reviewed_at_utc':'2026-11-04T15:10:00Z','rationale':'Time-limited, externally documented review exception.',
         'exception_approved_by':'risk_approver','exception_expires_utc':'2026-12-01T00:00:00Z'},
        {'disposition':'acknowledged','reviewer':'reviewer_beta','reviewed_at_utc':'2026-11-04T15:15:00Z','rationale':'Change corresponds to a documented inventory adjustment.'},
    ]
    for row, decision in zip(rows, decisions):
        row.update(decision)
    with (PLAN/'reviews.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    result = export_review_package(BASE, PLAN, PACKAGE, AS_OF)
    print(json.dumps({'changes':result['changes'],'tracked_actions':result['tracked_actions'],
                      'review_flags':result['review_flags']},indent=2))
    return result

if __name__ == '__main__':
    run()