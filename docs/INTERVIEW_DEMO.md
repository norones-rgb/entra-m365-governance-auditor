# Interview walkthrough — 5 minutes

1. **Business problem (30 sec):** Access grants, review campaigns, and audit trails often live in different platforms. A team needs a way to test whether privileged memberships have traceable approvals and review evidence.
2. **Design (45 sec):** Show `README.md`, `docs/ARCHITECTURE.md`, and the nine normalized CSV input schemas. Explain why offline, deterministic testing reduces tenant access requirements while building governance logic.
3. **Demo (90 sec):** Run `python run_demo.py` and open `reports/demo/dashboard.html`. Filter `High`, inspect missing approval, disabled member, guest access, and overdue campaign findings.
4. **Evidence (60 sec):** Open `evidence_correlations.csv`: demonstrate how a request ID links a IGA-style approval event and SIEM-style membership-change event. Show an `AUD-001` gap and explain that missing log exports are not automatically a control failure.
5. **Risk ownership (45 sec):** Show the approved exception for a privileged membership. Explain why exceptions are visible, time-limited, and not silent suppressions.
6. **Engineering discipline (30 sec):** Run unit tests, then discuss HTML escaping, CSV formula neutralization, and a future Microsoft Graph read-only connector.

## How to describe it on a resume

> Developed a Python-based identity-governance auditor that reconciles Entra-style privileged group memberships, SharePoint access, IGA-style approvals, and SIEM-style audit events; implemented control checks, exception tracking, searchable HTML reporting, CSV/JSON evidence exports, and automated tests using synthetic enterprise data.

**Say clearly:** It is an original *portfolio demonstration*, not production software deployed at a former employer. You did not configure Conditional Access or PIM as part of the project. Planned Microsoft Graph connectors are not yet implemented.
