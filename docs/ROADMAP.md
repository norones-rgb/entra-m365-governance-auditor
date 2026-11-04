# Roadmap

## v0.1 — completed (portfolio MVP)

- [x] Standardized CSV snapshots and validation
- [x] Nine access, SharePoint, campaign and audit evidence checks
- [x] Read-only, deterministic as-of evaluation
- [x] Approved and expiring exceptions
- [x] Interactive offline HTML, CSV/JSON exports and checksums
- [x] Synthetic demo and unit tests
- [x] CI workflow

## v0.2 — Microsoft integrations (not implemented)

- [ ] Microsoft Graph exporter for Entra groups, user status and direct memberships with pagination and least-privilege scopes
- [ ] Explicit transitive group membership handling
- [ ] SharePoint/PnP exporter with documented permission/inheritance model
- [ ] IGA export adapters and SIEM event/Log Analytics parsers, each mapping to normalized source schemas
- [ ] Import validation for deleted users, duplicate records, partial exports and source freshness
- [ ] Tenant-local report encryption and redaction options

## v0.3 — assessment depth (not implemented)

- [ ] Configurable controls, risk scoring and control ownership
- [ ] Optional Maester security assessment integration (where access is authorized)
- [ ] Conditional Access and PIM **read-only checks** with explicit limitations
- [ ] Robust exception and evidence review workflow with approval trails
- [ ] Baseline comparisons across snapshots and attested evidence packages

## Future commercial boundary

Keep the **public demo** synthetic and educational. If developed into a commercial offering, host private connectors, customer configuration, client evidence, integration credentials, and production controls separately. Never mix customer access data into this portfolio repository.
