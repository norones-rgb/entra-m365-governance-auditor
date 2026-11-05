# Selected-Scope Access Change Comparison (v0.5)

## Purpose

`compare-snapshots` compares **two previously collected, local, read-only exports** and identifies changes to **observed direct memberships and selected-site assignments**. The comparison makes no Microsoft Graph or SharePoint calls and does not change access.

**This is not a tenant-wide entitlement-drift or compliance assessment.** No user access decisions, approval provenance, historical grant timestamps, effective permissions or PIM/Conditional Access configurations are inferred.

## Run the synthetic example

```bash
python run_change_demo.py
```

Open `reports/change-demo/dashboard.html`. The sample is fabricated, reproducible and deliberately includes a scope change.

For independently authorized local snapshots:

```bash
python -m governance_auditor compare-snapshots \
  --before-graph exports/2026-10/selected-groups \
  --after-graph exports/2026-11/selected-groups \
  --before-sharepoint exports/2026-10/selected-site \
  --after-sharepoint exports/2026-11/selected-site \
  --output reports/2026-11-changes
```

The SharePoint pair is optional; omit **both** site flags for a Graph-only comparison. All input directories must be different and the output must not exist. On Windows PowerShell use a single-line command or backticks rather than the Bash `\` continuation character.

## Inputs

Graph inputs come from the optional v0.2+ `graph-export` snapshot: `manifest.json`, `groups.csv`, `users.csv`, `memberships.csv`, `non_user_members.csv`. Both snapshots must have timezone-aware `collected_at_utc`, valid selected group IDs, and consistent member references.

SharePoint inputs come from the optional v0.3+ selected-site PnP exporter: `manifest.json`, `sharepoint_group_members.csv`, `site_collection_admins.csv`, `root_web_role_assignments.csv`. The site URL in each row must match that export's manifest. Each time pair must be chronological.

## Interpretation and scope safety

- **Entra direct user and non-user membership additions/removals:** compared **only for group IDs selected in both snapshots**. If one export includes an extra group, its memberships are **not** called additions/removals. The non-overlapping group appears in `coverage.csv` as *not comparable*.
- **Entra account status:** compared only when the same user appears in both selected-group inventories. Other user absences do not mean their directory account was deleted.
- **Group metadata:** name, declared privileged flag and first-listed owner ID change are reported as metadata differences, not attested ownership changes.
- **SharePoint group roster, site collection admins and root-web role bindings:** compared only when the same site URL is used in both exports. A different site is a **coverage change**, not a mass revocation or grant. A SharePoint group's roster is not the user's effective permission set.
- **No actual grant timestamps:** a direct-membership addition between two snapshots indicates only a difference in observed membership; it does not establish when access was approved or granted. Removing a direct assignment does not prove all access has been removed.
- **No nested-group expansion, site inheritance, list/item permissions, sharing links, anonymous sharing, or revocation confirmation.** Separate inventories can be stale, and source retention may be incomplete.

## Output

- `changes.csv`: system, category, added/removed/changed, resource, principal, before, after, interpretation.
- `coverage.csv`: per-group and selected-site comparability plus count of selected directory users.
- `dashboard.html`: static, escaped offline summary and observations.
- `manifest.json`: source collection times, change counts, coverage warnings and SHA-256 checksums for local source files; checksums support tamper **detection only** and do not prove evidence authenticity or chain of custody.

Real exports contain security-sensitive principal and group identifiers. Store and distribute outside public source control, with appropriate access controls and retention policies. The public repository includes *only fabricated samples*.

## Known limitations

Only observations backed by comparable, explicitly selected source snapshots are reported. Role assignments and SharePoint group rosters don't demonstrate effective permissions; user status is collected only for members of selected groups. The comparison does not assess whether changes were authorized or malicious. Real tenant connectors have not been integration-tested here.
