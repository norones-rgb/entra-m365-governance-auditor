"""Offline, entirely fabricated sample of the v0.3 access review report."""
from __future__ import annotations
import datetime as dt
from pathlib import Path
from governance_auditor.graph_export import GraphClient
from governance_auditor.review_export import export_reviews

DEFINITION='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
INSTANCE='cccccccc-cccc-4ccc-8ccc-cccccccccccc'
ROOT='/identityGovernance/accessReviews/definitions/'+DEFINITION
MOCK = {
    ROOT: {'id':DEFINITION,'displayName':'Sample Quarterly Group Review'},
    ROOT+'/instances': {'value':[{'id': INSTANCE, 'status':'InProgress', 'startDateTime':'2026-10-01T00:00:00Z','endDateTime':'2026-11-01T00:00:00Z'}]},
    ROOT+'/instances/'+INSTANCE+'/decisions': {'value':[{'decision':'Approve'}, {'decision':'NotReviewed'}, {'decision':'NotReviewed'}]},
}
def mock(url, _token):
    return MOCK[url.removeprefix('https://graph.microsoft.com/v1.0')]

if __name__=='__main__':
    output = Path('reports/reviews-demo')
    result=export_reviews(GraphClient('synthetic-test-token',mock), [DEFINITION],output,dt.datetime(2026,11,4,tzinfo=dt.timezone.utc))
    print('Synthetic review-report demo:', result['instance_count'], 'instance(s). Open',output/'dashboard.html')
