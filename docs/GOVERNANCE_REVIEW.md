# Governance Review & Audit Evidence (v0.6)

**Offline, read-only, analyst-entered review workflow.** This module does not connect to Entra, SharePoint, an IGA tool or SIEM; it does not approve or revoke access. All public examples are fabricated. Real identity data, review decisions and evidence must remain outside this repository.

## Workflow

1. Generate a v0.5 `compare-snapshots` report (`changes.csv`, `coverage.csv`, `manifest.json`) over comparable selected scopes.
2. Initialize an evidence-anchored review plan:

   ```bash
   python -m governance_auditor review-init --comparison reports/changes --output reports/review-plan
   ```

3. Edit `reports/review-plan/reviews.csv` in a spreadsheet or text editor. Keep `change_id` unchanged and preserve all columns. Do not edit `source.json`.
4. Export the package for an explicitly chosen UTC review cutoff:

   ```bash
   python -m governance_auditor review-package --comparison reports/changes --plan reports/review-plan --output reports/review-evidence --as-of 2026-11-05T12:00:00Z
   ```

5. Open `reports/review-evidence/dashboard.html`. Review the CSV exports, coverage notes, and `package_manifest.json` with SHA-256 checksums. If a decision changes, generate a **new** package with a fresh output directory; preserve prior packages as separate snapshots.

To see a complete fabricated walkthrough:

```bash
python run_governance_demo.py
```

The public repository includes example output under `examples/governance_demo_output/`.

## Review fields

| Field | Meaning |
|---|---|
| `change_id` | Stable hash-derived ID from the eight canonical v0.5 change columns. Never edit. |
| `disposition` | `pending`, `acknowledged`, `investigate`, `remediate`, or `exception`. |
| `reviewer`, `reviewed_at_utc`, `rationale` | Required for any disposition other than `pending`. Timestamps must be timezone-aware. |
| `action_owner`, `action_due_utc`, `action_status` | Required for `investigate` or `remediate`; status is `open`, `in_progress` or `closed`. |
| `closure_evidence` | Reference supplied by the reviewer; required before marking an action `closed`. Its authenticity is **not validated**. |
| `exception_approved_by`, `exception_expires_utc` | Required for an `exception`. The named approver must differ from the reviewer; independently verify authority and approval. |

Unreviewed changes remain `pending`. An expired exception remains visible as `exception_expired`; overdue actions remain visible as `action_overdue`. The tool never silently suppresses a finding.

## Evidence package

- `reviewed_changes.csv`: source observation, reviewer disposition and status flags.
- `remediation_actions.csv`: separately filterable action queue.
- `coverage.csv`: source collection scope, including partial and non-comparable coverage.
- `dashboard.html`: standalone, escaped summary; no external assets.
- `package_manifest.json`: normalized status counts, review cutoff, input hashes and generated report hashes.

The plan stores hashes of its comparison source. Export refuses to run if the source files differ from the anchored versions, if review rows are missing/duplicated, or if required decision fields are inconsistent. New outputs use fresh directories and an atomic stage/rename pattern.

## Security and epistemic limits

- A filled `reviewer` or `exception_approved_by` column is a **self-reported assertion**, not an authenticated signature, delegated approval, verified policy exception, or authorization record. A closed action does not prove that access was revoked.
- Hashes detect accidental changes and support chain-of-custody *recordkeeping* but do **not** provide tamper-evident signatures or independent attestation. Anyone who controls both the source and its plan can recompute the hashes.
- `changes.csv` reports observed differences in selected scopes; it does not calculate nested/effective access, SharePoint item-level access or policy compliance. Never classify non-comparable scopes as grants or removals.
- Input reviewer names, rationales, references and observations may contain sensitive data. Keep them on authorized, access-controlled storage. `.gitignore` excludes `reports/` and `exports/`; do not commit live data.
- Results are not a substitute for official audit evidence collection or human review.