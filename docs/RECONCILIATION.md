# Offline SharePoint / Entra identity reconciliation (v0.4)

`reconcile-sharepoint` correlates **two locally exported, authorized snapshots**:

- A selected-group Entra Graph export from `graph-export`, containing `users.csv`, `groups.csv`, `manifest.json` and (starting with v0.4) `identity_aliases.csv`.
- A single selected-site PnP export containing `sharepoint_group_members.csv`, `site_collection_admins.csv`, `root_web_role_assignments.csv` and `manifest.json`.

The command reads files only. It performs **no tenant requests and makes no permission changes**. It is an **identity-correlation aid**, not an effective-access engine, compliance determination, access-review certification, or approval history.

## Offline synthetic example

```bash
python run_reconciliation_demo.py
```

View `reports/reconciliation-demo/dashboard.html`. All committed records use fabricated, reserved `.test` identities and fictional site names.

## Authorized local exports

```bash
python -m governance_auditor reconcile-sharepoint \
  --graph exports/selected-directory-snapshot \
  --sharepoint exports/selected-site-snapshot \
  --output reports/reconciliation-001
```

On Windows PowerShell, enter one line or use backticks rather than shell backslashes. The target output must not already exist and must be **outside the input directories**.

**Files written:**

- `identity_matches.csv`: one observation per source principal, resolution status, match method, matched directory object (if unique), and optional review indicator.
- `manifest.json`: source-schema provenance, source time-difference warning, observed match counts, and scope limitations.
- `dashboard.html`: static local summary; HTML-escaped untrusted principal values.

All three files may contain sensitive employee/guest identifiers and site-access information. Do **not** put live exports or reports into a public repository, CI artifact, issue, screenshot, or AI prompt without organizational authorization. Protect and dispose of them under the source organization's retention requirements.

## Matching method

The exporter fetches `userPrincipalName` and `mail` for **only the user objects encountered in selected groups**; both are written in a separate `identity_aliases.csv`. The user's existing normalized `users.csv` schema remains unchanged.

- An **exact** GUID (or recognized SharePoint Entra-group claims login) can match an exported Graph object ID. Unknown GUIDs are **out of selected scope** rather than presumed deleted identities.
- An exact, case-insensitive email-shaped alias in `i:0#.f|membership|<upn>`, a bare UPN, or a principal email can match a selected Graph user via the exported UPN or mail aliases. Display names and partial string matches are never used.
- If an alias resolves to multiple Graph identities, or the source's explicit type disagrees with its identity match, the result is **ambiguous**, with no chosen identity.
- SharePoint-local groups are **out of scope** for direct Entra identity matching. A GUID-matched Entra group is not expanded into users.
- A uniquely matched **disabled user** in a directly exported SharePoint principal row gets a *review indicator*. It is **not proof of effective access or a security violation**.

| Resolution | Interpretation |
|---|---|
| `matched` | One selected directory user or group matched exactly |
| `ambiguous` | Multiple possible users or a source-type conflict; no identity selected |
| `unresolved` | No supported identifier or matching alias in the selected export |
| `out_of_scope` | SharePoint-local group or GUID not among exported directory objects |

## Essential boundaries

- Graph's source contains only **selected groups**, directly listed user members and current account status. It is not a full directory inventory. An identity missing from the exported data is **not necessarily absent from the tenant**.
- PnP's source contains one selected site's group roster, site admins and root-web assignments; there is **no inheritance traversal, nested group expansion, sharing-link enumeration, or file/item-level permissions**.
- The current system does **not** determine membership grant timestamps, access request approval validity, access review reviewer identity, or PIM state.
- Principal claims may differ by tenant and authentication mode. The parser intentionally handles a small strict subset. Verify and expand claim parsing using independent samples in an authorized test environment before operational deployment.
- The manifest shows whether the two source snapshots were more than **72 hours apart**; this is a *freshness warning*, not proof of a change or policy breach. Same-time exports still cannot guarantee causal or complete evidence.
- Earlier v0.2 Graph exports lacking `identity_aliases.csv` are accepted but will usually produce fewer user matches; the tool never invents identities from display names.
- A match across exports is not proof that the snapshots belong to the same identity tenant; cross-tenant correlation has not been established.

## Security and validation

The command validates required CSV headers, unique Graph user/group IDs, alias ownership, supported manifest schemas, consistent selected-site URLs and report output isolation. Malformed sources fail rather than writing a partial report. CSV output is formula-injection neutralized and dashboard text is HTML-escaped.

The integration has been tested only with **synthetic CSVs**, not real tenant identities or PowerShell execution. Always review source coverage, delegated permissions, and sensitive data handling before using real exports.