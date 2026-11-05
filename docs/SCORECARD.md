# v0.7 — Governance workflow scorecard

The scorecard is a **local, read-only report about the review process**, built from a v0.6 review evidence package. It is **not** a security posture grade, audit certification, measure of effective permissions, or independently attested approval. It does not connect to Microsoft 365, Entra ID, or SharePoint.

## Run the synthetic demonstration

```bash
python run_scorecard_demo.py
```

Open `reports/scorecard-demo/dashboard.html`, or inspect the committed synthetic report at `examples/scorecard_demo_output/dashboard.html`.

## Run on your own *authorized* local v0.6 package

```bash
python -m governance_auditor governance-scorecard \
  --package reports/governance-demo/package \
  --output reports/my-scorecard \
  --as-of 2026-11-15T12:00:00Z
```

The new output directory must not exist and must be outside the source directories. Optionally add `--comparison /path/to/v0.5-comparison` and `--plan /path/to/v0.6-review-plan` to verify that those original source files still match the hashes recorded in the evidence package.

## Metric definitions

| Metric | Numerator | Denominator | Interpretation |
|---|---|---|---|
| Reviews documented | Non-`pending` dispositions | All selected observed changes | Documented, **self-reported** analyst review; not identity verification |
| Open actions within due date | Non-closed tracked actions not overdue | All non-closed tracked actions | Timeliness at the requested UTC `--as-of`; `closed` is excluded, not considered verified |
| Exceptions not expired | Exception dispositions with an expiration on/after `--as-of` | All exception dispositions | Currency of *recorded* exception claims, not validation of approver authority |
| Comparable selected scopes | Source scope entries marked `yes` | All source scope entries, including `no` and `partial` | Comparability only among **explicitly selected** exports; not tenant coverage |
| Closed actions with references | Closed actions with a recorded closure reference | All closed tracked actions | A reference exists; the referenced evidence is **not** opened or independently checked |

When a denominator is zero, the metric is **N/A**, not 100%. There is no composite security score. The qualitative `readiness` label is a workflow follow-up indicator, not an assurance rating.

## Example synthetic results

The sample evidence package contains 9 changes, 4 pending reviews, 2 tracked open actions, 1 exception and 4 collection scope entries. As of **2026-11-15 12:00 UTC**, both tracked actions are past due, the exception is still current, and two of four scopes are comparable. This is illustrative data, not a live assessment.

## Validation and output

The tool checks the v0.6 package schema, required files, file digests, row counts, disposition flags, duplicate IDs, and action-record consistency. Optionally, it also checks the original v0.5 comparison and v0.6 plan against the stored file digests. If any supplied evidence fails checks, it stops **without** creating a partial scorecard.

- `scorecard.json`: metrics, counts, source-validation status, and limitations
- `scorecard.csv`: machine-readable metric rows
- `action_queue.csv`: change ID, owner, due date, status, and re-evaluated due indicator
- `dashboard.html`: static offline overview with escaped input values
- `manifest.json`: SHA-256 digests of the generated files and references to the validated local source package

The date is supplied explicitly and must not predate the evidence package. Overdue and expired states are recomputed using the supplied date; the original review package is never modified.

### Trust boundaries

All reviewer/approver names, decisions, and closure references in the input remain **self-reported claims**. A source hash stored alongside the source is not a digital signature, chain of custody, or independent proof of control effectiveness. For real audit use, add authenticated reviewers, controlled storage, retention, corroboration of remediation, signed attestation, and approved governance policies outside this demo. Never publish real exports or real reviewers' information.