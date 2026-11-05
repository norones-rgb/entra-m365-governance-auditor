# Selected SharePoint Online site inventory (v0.3)

`sharepoint/Export-SitePermissions.ps1` is an **optional read-only PnP PowerShell collection script** for one explicitly selected SharePoint Online site. It inventories three source views: **site collection administrators**, **SharePoint group memberships**, and **root web role assignments**.

This script's collection commands follow documented PnP interfaces but **have not been tested against a live tenant**. A PowerShell/PnP integration test in an authorized test environment is required before operational reliance.

## Requirements

- PowerShell 7.2+ and current `PnP.PowerShell` module; see the module's current runtime requirements for your installed version.
- Tenant-approved Entra app registration with a public client ID and SharePoint delegated read access appropriate for the selected site.
- An account authorized to read group memberships, role assignments and site collection administrator records. Some calls may require elevated permission; if any fail, the export aborts rather than silently claiming completeness.
- A selected SharePoint site URL like `https://<tenant>.sharepoint.com/sites/<site>` (or `/teams/<site>`); no site discovery or tenant-wide crawl.
- An approved local storage location outside any public repository.

```powershell
Install-Module PnP.PowerShell -Scope CurrentUser
./sharepoint/Export-SitePermissions.ps1 -SiteUrl 'https://<tenant>.sharepoint.com/sites/<site>' -ClientId '<PUBLIC-CLIENT-GUID>' -OutputDirectory 'exports/selected-site-2026-11-04'
```

The script requires interactive authentication with an app registration, and uses read commands only: `Get-PnPWeb`, `Get-PnPGroup`, `Get-PnPGroupMember`, `Get-PnPSiteCollectionAdmin`, and `Get-PnPProperty`. It writes results to a **new** output directory only after all source queries succeed.

## Outputs

| File | What it contains |
|---|---|
| `sharepoint_group_members.csv` | Members explicitly returned for SharePoint groups on the selected site, with group ID, login, email and principal type |
| `site_collection_admins.csv` | Site collection administrators returned by PnP for the selected site |
| `root_web_role_assignments.csv` | Principal, type, and role definitions assigned on the site's root web |
| `manifest.json` | Capture time, site URL, counts, explicit scope exclusions and limitations |

## Major limitations

This is an **inventory, not effective permissions**. It does not expand Entra or Microsoft 365 groups, enumerate external sharing links, resolve item/library-level unique permissions, assess subsites, determine account enabled/disabled status, classify guests, calculate sharing policy posture, or infer historical grant/approval dates.

Do not feed its group roster directly into `site_permissions.csv` in the audit engine: that schema expects resolved user identity, role, and historical grant fields that this exporter cannot substantiate. A future adapter must reconcile identities against an independently authorized directory snapshot and document gaps.

## Security practices

Exports contain personally identifiable information and potentially sensitive access structure. Never share the real files publicly, commit them, or include tenant identifiers in issues/README. Run only against authorized sites and follow applicable retention and access controls. The `exports/` directory is Git-ignored.

## PnP documentation

- [Get-PnPGroupMember](https://pnp.github.io/powershell/cmdlets/Get-PnPGroupMember.html)
- [Get-PnPSiteCollectionAdmin](https://pnp.github.io/powershell/cmdlets/Get-PnPSiteCollectionAdmin.html)
- [Get-PnPWeb](https://pnp.github.io/powershell/cmdlets/Get-PnPWeb.html)
- [Get-PnPProperty](https://pnp.github.io/powershell/cmdlets/Get-PnPProperty.html)
- [Connect-PnPOnline](https://pnp.github.io/powershell/cmdlets/Connect-PnPOnline.html)

## Identity correlation (v0.4)

A separate, offline correlation command can now compare these PnP principal rows against a selected Entra Graph snapshot, provided both exports were authorized and retained locally. Only strict identifiers and user aliases are matched; SharePoint-local groups, nested membership, effective permissions, and approval validity remain unknown. Read [RECONCILIATION](RECONCILIATION.md) before use.