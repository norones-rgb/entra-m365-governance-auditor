# Entra & Microsoft 365 Access Governance Auditor

**An offline, read-only portfolio project for identity governance, SharePoint access oversight, and audit evidence reconciliation.**

[![Tests](https://github.com/norones-rgb/entra-m365-governance-auditor/actions/workflows/tests.yml/badge.svg)](https://github.com/norones-rgb/entra-m365-governance-auditor/actions/workflows/tests.yml) · **Python 3.11+** · Dependency-free offline engine · Optional MSAL for Graph · Synthetic dataset included

> **Version 0.2:** The auditor still runs offline against normalized CSV. An **optional read-only Graph exporter** can collect selected Entra groups and direct user memberships after explicit authorized sign-in. It does not connect to SharePoint, IGA/SIEM, or evaluate real tenant policies. The public demo and all samples use fabricated data.

## Why this exists

Enterprise identity governance is more than granting access. Teams need to establish **who currently has permissions, why those permissions were approved, when they were reviewed, and what evidence can support an audit**. This project brings those questions into a single, repeatable analysis of normalized snapshots.

![Sample audit dashboard](assets/dashboard-preview.png)

### Capabilities

- **Privileged Entra-group governance:** Flag memberships missing a current approval, approvals occurring after access was granted, disabled users retaining elevated membership, and privileged groups without documented owners.
- **SharePoint access reviews:** Flag guests on sensitive sites without current site-access approvals, disabled users retaining exported permissions, and sites without recorded owners.
- **Governance campaigns:** Identify overdue user-access-review and job-role-review campaigns.
- **IGA + SIEM-style evidence:** Match synthetic approval and membership-change events by request ID, user, and resource; separately report gaps where a matching event pair is absent.
- **Exceptions and auditability:** Apply time-limited, approved exceptions without deleting findings. Produce JSON, CSV, HTML, correlation evidence, source-file hashes, and output checksums.

## Quick start (Windows PowerShell, macOS, Linux)

Python 3.11 or newer is required. No `pip install` is needed.

```bash
python run_demo.py
```

Open `reports/demo/dashboard.html` in a browser. Or inspect the pre-generated synthetic example at [`examples/demo_output/dashboard.html`](examples/demo_output/dashboard.html). The demo is deliberately pinned to **2026-11-04**, keeping its findings reproducible.

Or supply your own normalized CSV snapshot:

```bash
python -m governance_auditor scan \
  --input examples/synthetic \
  --output reports/manual \
  --as-of 2026-11-04
```

On Windows PowerShell, place the command on one line, or replace `\` with backticks.

**Outputs:** `dashboard.html` (standalone, searchable/filterable), `findings.csv`, `findings.json`, `evidence_correlations.csv`, and `report_sha256.txt`.

## Optional live Microsoft Graph inventory (v0.2)

The `graph-export` command collects a **partial** inventory for explicitly selected Entra group GUIDs, with delegated, read-only permissions. It does not write to the tenant or fabricate approval evidence, group grant timestamps, or SharePoint permissions. **It is not a full audit.**

```bash
python -m pip install -r requirements-graph.txt
python -m governance_auditor graph-export --tenant-id <TENANT-GUID> --client-id <APP-GUID> --group-id <GROUP-GUID> --output reports/graph-example
```

Read [Graph exporter setup and limitations](docs/GRAPH_EXPORT.md) before using real tenant access. All real exports must stay outside public source control.

## Controls

| ID | Severity | Check |
|---|---|---|
| PRV-001 | High | Privileged Entra-group membership has no approved, unexpired request in the snapshot |
| PRV-002 | High | Approval date follows granted date |
| PRV-003 | High | Disabled user retains privileged group membership |
| PRV-004 | Medium | Privileged group has no recorded owner |
| SP-001 | High | Guest/external identity on restricted/confidential SharePoint site lacks current site approval |
| SP-002 | Medium | SharePoint site has no recorded owner |
| SP-003 | Medium | Disabled user retains an exported SharePoint permission |
| REV-001 | Medium | User access / job role / other access-review campaign is overdue |
| AUD-001 | Medium | Approved privileged membership has no correlated IGA and SIEM log-event pair |

**Interpretation:** These are configurable *governance hypotheses*, not definitive security findings. For example, an absent approval or event may simply mean the export has incomplete coverage. The `AUD-001` control models an organization that expects both log streams and consistent request IDs; it is **not** an assertion that every environment must produce those two events.

## Synthetic demonstration

The dataset includes invented identities, privileged groups, knowledge-library-style SharePoint sites, access requests, user access and job-role campaigns, SIEM/IGA-style events, and one approved time-limited exception. The demonstration produces **10 open findings, 1 excepted finding, and 2 correlated evidence pairs** as of November 4, 2026.

## Tests

```bash
python -m unittest discover -s tests -v
```

CI runs the offline engine and Graph mock tests, plus the synthetic scenario, through GitHub Actions on push and pull request. No tenant credentials are needed.

## Repository map

```text
├── governance_auditor/
│   ├── __main__.py      # CLI
│   ├── engine.py        # Snapshot validator and rule engine
│   └── reporting.py     # Offline HTML, JSON, CSV, checksums
├── examples/synthetic/  # Invented, reproducible sample records
├── examples/demo_output/  # Pre-generated demonstration reports
├── assets/dashboard-preview.png
├── requirements-graph.txt  # Optional MSAL auth dependency
├── tests/               # Regression, safety and validation tests
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DATA_DICTIONARY.md
│   ├── CONTROL_RATIONALE.md
│   ├── SECURITY.md
│   ├── INTERVIEW_DEMO.md
│   ├── GRAPH_EXPORT.md
│   └── ROADMAP.md
└── .github/workflows/tests.yml
```

## What the app does *not* do

- Graph supports **selected groups and direct user memberships only**. No PnP PowerShell/SharePoint authentication yet.
- No Conditional Access, PIM policy configuration, Intune, endpoint compliance, or tenant security hardening checks.
- No transitive/nested group resolution, dynamic group expansion, SharePoint inheritance traversal, or effective-permissions calculation.
- No certification of regulatory compliance, automatic revocation, or auto-remediation.
- No guarantee of completeness if source systems have inconsistent IDs, missing activity, retention gaps, or inaccurate exported owners.

Read [ARCHITECTURE](docs/ARCHITECTURE.md), [DATA DICTIONARY](docs/DATA_DICTIONARY.md), and [SECURITY](docs/SECURITY.md) before running on anything other than synthetic data.

## Professional context

This is an independent demonstration using **fabricated identities, fictional resource names, and simulated audit events**. It does not describe, reproduce, or represent systems, controls, records, security findings, or operations at any real organization. All project documentation and sample data are intentionally organization-neutral.

## License

A license has **not yet been selected**. Before publishing publicly, review [LICENSING.md](LICENSING.md) to decide whether this is portfolio-only source or a permissively licensed open-source demo. Customer data and proprietary commercial integrations do not belong in this repository.