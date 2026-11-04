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
- [ ] Auditable identity correlation and coverage mapping between Graph/PnP output and local evaluation schemas

## v0.4 — deeper assessment (not implemented)

- [ ] Configurable controls, risk scoring and control ownership
- [ ] Optional Maester security assessment integration (where access is authorized)
- [ ] Conditional Access and PIM **read-only checks** with explicit limitations
- [ ] Robust exception and evidence review workflow with approval trails
- [ ] Baseline comparisons across snapshots and attested evidence packages

## Future commercial boundary

Keep the **public demo** synthetic and educational. If developed into a commercial offering, host private connectors, customer configuration, client evidence, integration credentials, and production controls separately. Never mix customer access data into this portfolio repository.
