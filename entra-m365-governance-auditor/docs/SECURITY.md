# Security and privacy guardrails

1. **Synthetic-first:** The committed example is invented. No real user, access, ticket, log, or company information should enter a public demo repository.
2. **Read-only by construction:** The code reads local CSVs and writes local reports. No Microsoft Graph tenant authentication, mutation endpoints, secrets, or network calls are present.
3. **Least privilege in later versions:** A live connector should use only needed Microsoft Graph/PnP read scopes, explicit administrator consent, and protected credentials; do not request broad write scopes for a read-only assessment.
4. **Sensitive reports:** Findings can reveal privileged group names, approval history, access paths, and sensitive sites. Store exports in secure locations; do not commit real exports or generated reports to GitHub.
5. **Protect output consumers:** HTML dynamically escapes record values; generated CSV cells with formula prefixes are neutralized before spreadsheet opening. Review any additional report format carefully.
6. **Audit verifiability:** Source and report SHA-256 hashes support reproducibility, but a checksum stored alongside a modified report does not establish authenticity. For audit attestation, use signed manifests and trusted storage.
7. **Human approval:** The tool makes no access changes and does not recommend automatic revocation from a finding alone.
8. **No certification claim:** Findings are heuristics over normalized snapshots, not proof of compliance with any particular framework.

## Before enterprise deployment

Perform an explicit data privacy review, threat model, group-membership effective-access review, tool dependency review, role-based access design, credential storage design, export permission review, and audit of source completeness. Introduce secure storage, authorization, retention controls, exception expiry workflow, and signed evidence before representing results as official evidence.
