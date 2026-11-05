# Roadmap

## v0.1 — completed (portfolio MVP)

- [x] Standardized CSV snapshots and validation
- [x] Nine access, SharePoint, campaign and audit evidence checks
- [x] Read-only, deterministic as-of evaluation
- [x] Approved and expiring exceptions
- [x] Interactive offline HTML, CSV/JSON exports and checksums
- [x] Synthetic demo and unit tests
- [x] CI workflow

## v0.2 — Optional Microsoft Graph selected-group exporter

- [x] Delegated Microsoft Graph selected-group exporter for group owners, user status and direct memberships with pagination and read-only scopes
- [x] Explicit limitation manifest, no invented grant dates or approval evidence, network-free connector tests
- [ ] Explicit transitive group membership handling
- [x] SharePoint/PnP **selected-site** group/site-admin/root-web permission inventory; live tenant integration **unverified**
- [ ] IGA export adapters and SIEM event/Log Analytics parsers, each mapping to normalized source schemas
- [ ] Import validation for deleted users, duplicate records, partial exports and source freshness
- [ ] Tenant-local report encryption and redaction options

## v0.3 — selected access reviews and SharePoint inventory

- [x] Read-only Graph selected-review definitions, instances, decision-count snapshots, and HTML report
- [x] Offline synthetic access-review demo, test coverage, and documentation
- [x] Optional PnP selected-site SharePoint inventory script (requires live test and authorized tenancy)
- [ ] Validated live PnP/Graph permission and paging integration against an explicitly authorized test tenant
- [x] Offline strict-identifier matching of Graph/PnP exports with explicit match and coverage reports (v0.4, synthetic-tested)

## v0.4 — offline identity correlation

- [x] Exact GUID, UPN, and mail correlation for exported SharePoint principals
- [x] Separate Graph alias inventory without changing the existing normalized user schema
- [x] Ambiguous and out-of-scope classifications, disabled-account review indicators, source provenance
- [x] HTML/CSV export and regression-tested synthetic demonstration
- [ ] Live test against explicitly authorized Entra and SharePoint tenant

## v0.5 — selected-scope access change detection

- [x] Compare two chronological, locally exported selected-group Entra snapshots
- [x] Identify direct membership changes, user status and group metadata differences only in common collection scope
- [x] Compare matching selected-site SharePoint rosters, root-web role assignments and site collection administrators
- [x] Flag changed source scope as non-comparable instead of inventing grants or removals
- [x] Output CSV, provenance-hashed JSON manifest and static HTML dashboard with a synthetic regression demo
- [ ] Validation with explicitly authorized real historical snapshots (not included in public repository)

## v0.6 — offline governance review and audit evidence

- [x] Stable change IDs pinned to a specific source comparison with SHA-256 hashes
- [x] Analyst disposition template (pending, acknowledged, investigate, remediate, exception)
- [x] Remediation owner/due/status tracking and time-limited exception handling
- [x] Action/exception validation and separate reporting without auto-remediation
- [x] Offline HTML, CSV and manifest evidence bundle with source and output digests
- [x] Synthetic scenario, CLI documentation and network-free regression tests
- [ ] Verified reviewer identity, policy approvals or cryptographic evidence attestation (not provided by the offline prototype)

## v0.7 — selected-scope workflow scorecard

- [x] Validate v0.6 evidence package digests and internal review/action consistency before scoring
- [x] Summarize documented reviews, open action timeliness, recorded exception currency and comparable selected source scopes
- [x] Re-evaluate overdue and expired indicators against an explicit timezone-aware date
- [x] Optional hash checks against original v0.5 comparison and v0.6 review plan
- [x] N/A denominators, separate metrics, no composite enterprise security or compliance grade
- [x] Static offline HTML, CSV and JSON reports with output checksums and synthetic demo
- [ ] Authenticated approvals, independently verified closure, signed evidence and formal control ownership

## Future — deeper assessment (not implemented)

- [ ] Configurable controls, risk scoring and control ownership
- [ ] Optional Maester security assessment integration (where access is authorized)
- [ ] Conditional Access and PIM **read-only checks** with explicit limitations
- [x] Offline, self-reported exception and evidence review worksheet (v0.6; no authenticated approvals)
- [x] Selected-source baseline comparisons across snapshots (v0.5; not attested evidence)
- [ ] Attested evidence package and reviewer signoff flow

## Future commercial boundary

Keep the **public demo** synthetic and educational. If developed into a commercial offering, host private connectors, customer configuration, client evidence, integration credentials, and production controls separately. Never mix customer access data into this portfolio repository.