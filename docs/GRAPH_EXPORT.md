# Optional Microsoft Graph exporter (v0.2)

This optional connector exports a **partial, read-only Entra group inventory** from Microsoft Graph v1.0. It is not a tenant audit and does **not** connect to SharePoint, Conditional Access, PIM or IGA/SIEM platforms.

## Prerequisites

- Python 3.11+; `pip install -r requirements-graph.txt` for MSAL authentication.
- A Microsoft Entra app registration configured as a **public client** with device-code flow enabled, with permission to use delegated **Group.Read.All** and **User.Read.All** scopes. A tenant administrator may need to grant consent. Do not create client secrets for this tool.
- A signed-in work or school account with appropriate directory/group read privileges; OAuth scopes alone do not guarantee access.
- Explicit GUIDs for the individual groups you are authorized to review. The exporter does not enumerate every group by default.
- Organizational authorization to export identities and memberships to an approved local device or environment.

## Example (PowerShell)

```powershell
python -m pip install -r requirements-graph.txt
python -m governance_auditor graph-export --tenant-id '<TENANT-GUID>' --client-id '<PUBLIC-CLIENT-APP-GUID>' --group-id '<GROUP-GUID>' --privileged-group-id '<GROUP-GUID>' --output reports/graph-2026-11-04
```

Use a fresh output directory for each run. The program displays the Microsoft sign-in instructions for the **MSAL device-code flow**; no tokens, credentials, or token cache are written to disk by this code. Never place sensitive real tenant data into a public repository, issue, or CI log.

## Output

| File | Scope |
|---|---|
| `users.csv` | Distinct directly returned user objects, with current accountEnabled status |
| `groups.csv` | Explicitly selected groups, human-readable name, explicit privilege classification, first returned owner identifier |
| `memberships.csv` | **Direct user-to-group edges only**, with `granted_at` left **blank** because the API doesn't provide the historical grant timestamp |
| `non_user_members.csv` | Device, group, service-principal, or unknown member IDs and types; explicitly **not evaluated** |
| `identity_aliases.csv` | Selected users' available UPN and mail aliases for **offline exact-match reconciliation** (v0.4) |
| `manifest.json` | UTC collection time, source and coverage limitations, record counts, owner counts, and missing evidence types |

Successful outputs are created only after all selected groups are processed. Requests use HTTP **GET** exclusively. The program rejects pagination redirects to unapproved hosts and retries limited Graph throttling responses. Authentication and HTTP errors cause the export to stop.

## Important limitations

- This only inventories **specified groups**. It does not calculate nested/transitive group or effective user membership, expand dynamic group rules, identify PIM eligible assignments, or verify local administrator status on endpoints.
- Graph v1.0 `GET /groups/{id}/members` has a documented service-principal listing limitation. The absence of a principal is **not** proof that no principal belongs to a group.
- Graph can return incomplete properties when a token lacks read permission for a member type. This exporter lists non-user objects as unassessed, and stops on incomplete user-account status to avoid false assertions.
- Owner metadata is simplified: the CSV stores the first owner ID for compatibility with the v0.1 engine; `manifest.json` reports how many owners were returned.
- The tool cannot determine *when* a membership was granted. The audit engine supports blank `granted_at` and **does not run approval-after-grant control PRV-002** when it is unknown.
- **Never interpret missing approval records as rejected or nonexistent approvals.** The v0.2 exporter does not create approvals, sites, campaigns, exceptions, or audit events. The existing full `scan` command requires those independent evidence tables, and should be used only when source coverage is evaluated and documented. Do not create empty placeholders to make the scan run.
- Local output may contain personal information or organizational security metadata. Retain under approved controls, restrict access, and securely dispose of files after use. `reports/` and `exports/` are Git-ignored by default.

## API documentation

- [List group direct members](https://learn.microsoft.com/en-us/graph/api/group-list-members?view=graph-rest-1.0)
- [List group owners](https://learn.microsoft.com/en-us/graph/api/group-list-owners?view=graph-rest-1.0)
- [Get user](https://learn.microsoft.com/en-us/graph/api/user-get?view=graph-rest-1.0)
- [MSAL Python token acquisition](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens)

## Offline reconciliation (v0.4)

Selected user UPN and mail aliases now export into `identity_aliases.csv`; `users.csv` retains its original schema. These aliases are sensitive and may be absent or nonunique. They can be used in the optional offline SharePoint reconciliation command, which reports unresolved/ambiguous matches instead of guessing. See [RECONCILIATION](RECONCILIATION.md).