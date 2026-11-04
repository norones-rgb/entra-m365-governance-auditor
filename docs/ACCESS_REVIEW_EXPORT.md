# Selected access-review inventory (v0.3)

This **read-only**, optional Graph v1.0 connector summarizes explicitly selected Entra access-review definitions, their instances and the counts of their decision statuses. It does **not** download individual reviewed principals or reviewer names, modify campaigns, approve or deny access, or claim regulatory compliance.

## Requirements

- Python 3.11+ and `python -m pip install -r requirements-graph.txt` (MSAL only).
- An Entra **public client** app registration with delegated `AccessReview.Read.All` permission and any required administrative consent.
- An authorized work/school account with a qualifying Entra role or permission to read the selected review definitions. Permission consent alone may be insufficient.
- One to 20 **specific access review definition GUIDs** approved for inspection. No broad enumeration is performed.
- An authorized device/location for potentially sensitive campaign metadata. Real exports must remain **outside public GitHub**.

## Syntax

```powershell
python -m governance_auditor review-export --tenant-id '<TENANT-GUID>' --client-id '<APP-GUID>' --definition-id '<REVIEW-DEFINITION-GUID>' --output reports/review-2026-11-04
```

Optionally pass `--as-of 2026-11-04T12:00:00-05:00` for a timezone-aware snapshot. Repeat `--definition-id` to select multiple campaigns. The tool prompts for Microsoft device-code sign-in and does not write token material to the project. Outputs must go to a **new** folder, ideally under the Git-ignored `reports/`.

## Outputs

| File | Description |
|---|---|
| `review_instances.csv` | Selected definition ID and display name, instance ID, review status, start and due time, overdue indicator, counts of approve/deny/not-reviewed/other decisions |
| `dashboard.html` | Standalone, HTML-escaped review status dashboard with summary counters; no participant or reviewer identities |
| `manifest.json` | UTC collection and evaluation timestamps, selected definition IDs, count, declared limits and limitations |

### Operational interpretation

- An **overdue indicator** means an instance has an end timestamp before the selected evaluation time and was not returned in `Completed` or `AutoReviewed` state. This is a **screening indicator**, not a finding that the review was mishandled.
- An absent due date is **unknown**, never automatically overdue.
- `NotReviewed` decisions are counted as returned by the API; different review setups, auto-decisions, and multi-stage campaigns may require deeper analysis.
- This version does **not** correlate review decisions to privileged group membership approvals and does not synthesize campaign rows for the v0.1 `scan` engine. These are separate evidence streams and cannot responsibly be merged without a mapping and coverage model.
- No participant ID, reviewer ID, individual rationale, or decision timestamps are exported. Depending on the authorized review configuration, Graph may still return sensitive objects in memory while counts are calculated.
- HTTP failures, incomplete pages, malformed review IDs or invalid date fields abort the export before output is committed; existing output directories are never overwritten.

## Offline demo

```bash
python run_review_demo.py
```

Open `reports/reviews-demo/dashboard.html`. The demo uses only mocked HTTP responses and fictional records; no Microsoft sign-in is required.

## Official API references

- [List review instances](https://learn.microsoft.com/en-us/graph/api/accessreviewscheduledefinition-list-instances?view=graph-rest-1.0)
- [List review decisions](https://learn.microsoft.com/en-us/graph/api/accessreviewinstance-list-decisions?view=graph-rest-1.0)
- [Get review definition](https://learn.microsoft.com/en-us/graph/api/accessreviewscheduledefinition-get?view=graph-rest-1.0)
