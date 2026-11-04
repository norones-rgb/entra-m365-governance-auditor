# Security and privacy guardrails

1. **Synthetic-first:** The committed example is invented. No real user, access, ticket, log, or company information should enter a public demo repository.
2. **Read-only by construction:** The offline audit engine never accesses a tenant. The **optional** Graph and PnP collectors authenticate only with explicit user action, use read-only API calls to selected objects, and write snapshots locally; no tenant mutation calls or client secrets are included. Live PnP integration is not yet verified.
3. **Least privilege:** Graph group export uses `Group.Read.All` and `User.Read.All`; review export uses `AccessReview.Read.All`. Both require signed-in authorized access and potentially administrator consent/roles. PnP uses a site-scoped interactive connection; avoid unnecessary permission grants. No write scopes are requested by the code.
4. **Sensitive reports:** Findings can reveal privileged group names, approval history, access paths, and sensitive sites. Store exports in secure locations; do not commit real exports or generated reports to GitHub.
5. **Protect output consumers:** HTML dynamically escapes record values; generated CSV cells with formula prefixes are neutralized before spreadsheet opening. Review any additional report format carefully.
6. **Audit verifiability:** Source and report SHA-256 hashes support reproducibility, but a checksum stored alongside a modified report does not establish authenticity. For audit attestation, use signed manifests and trusted storage.
7. **Human approval:** The tool makes no access changes and does not recommend automatic revocation from a finding alone.
8. **No certification claim:** Findings are heuristics over normalized snapshots, not proof of compliance with any particular framework.

## Before enterprise deployment

Perform an explicit data privacy review, threat model, group-membership effective-access review, tool dependency review, role-based access design, credential storage design, export permission review, and audit of source completeness. Introduce secure storage, authorization, retention controls, exception expiry workflow, and signed evidence before representing results as official evidence.

## v0.3 clarification

Never conflate selected review **decision counts** with independently verified approval evidence. The SharePoint group/site-admin/root-web inventory does not resolve effective permissions or item-level inheritance. Exported directories are Git-ignored, but public issue attachments, screenshots, and CI logs also require caution. No real tenant validation is claimed for the new collectors.
