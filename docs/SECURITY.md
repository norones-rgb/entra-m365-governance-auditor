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

## Cross-source reconciliation outputs (v0.4)

Offline reconciliation can include source principal emails, login names and directory object IDs. These are sensitive, so never commit real reports or export snapshots, share them publicly or place them in CI artifacts. The source modules do not make Graph/SharePoint mutations. The matching is limited to strict identifiers and never guesses ambiguous identities or claims effective permissions. See [RECONCILIATION](RECONCILIATION.md).

## v0.5 comparison privacy and scope

Change reports contain identifiers, security group memberships and site principal observations and must remain local/private. The generated dashboard HTML escapes source text; CSV output neutralizes common spreadsheet formula prefixes. The comparator reads only explicit local source directories; it makes no network calls or tenant mutations and rejects existing output paths to avoid overwriting evidence. Source hashes detect changed files but are not an attestation or guarantee of provenance. Changed collection scope suppresses access-change claims for non-overlapping resources. Keep real snapshot directories and generated reports outside GitHub.

## Offline review data (v0.6)

Reviewer identifiers, rationale, exception approval assertions and closure references may be sensitive. Treat review plans and packages as controlled local records. The tool cannot independently verify reviewer identity, approved exceptions, actual removal of access, or the completeness of submitted evidence. Source/output SHA-256 hashes are for consistency and provenance, **not** cryptographic attestation. Never commit real review files or exports to this public demonstration repository.