#Requires -Version 7.2
<#
.SYNOPSIS
  Read-only PnP PowerShell export of one explicitly selected SharePoint Online site.
.DESCRIPTION
  Inventories site collection admins, SharePoint group rosters and ROOT-WEB role assignments.
  Does not calculate effective access, enumerate sharing links, or traverse lists/items.
  Run only with permission to inspect the selected site. Never commit live exports.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$SiteUrl,
  [Parameter(Mandatory=$true)][guid]$ClientId,
  [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function SafeCell([object]$Value) {
  if ($null -eq $Value) { return '' }
  $text = [string]$Value
  if ($text -match '^\s*[=+\-@]') { return "'$text" }
  return $text
}
function Export-SafeCsv([object[]]$Rows, [string[]]$Fields, [string]$Destination) {
  $prepared = foreach($item in $Rows) {
    $properties = [ordered]@{}
    foreach($field in $Fields) { $properties[$field] = SafeCell $item.$field }
    [pscustomobject]$properties
  }
  if (@($prepared).Count -gt 0) {
    @($prepared) | Export-Csv -NoTypeInformation -Encoding utf8 -Path $Destination
  } else {
    # Header-only CSV; no falsely synthesized records.
    ('"' + ($Fields -join '","') + '"') | Set-Content -Encoding utf8 -Path $Destination
  }
}

try { $site = [uri]$SiteUrl } catch { throw 'SiteUrl must be an absolute SharePoint Online URL.' }
if ($site.Scheme -ne 'https' -or $site.Host -notmatch '^[a-z0-9-]+\.sharepoint\.com$' -or
    $site.Port -ne 443 -or $site.UserInfo -or $site.Query -or $site.Fragment -or
    $site.AbsolutePath -notmatch '^/(sites|teams)/[a-zA-Z0-9_.~-]+/?$') {
  throw 'Provide one explicit https://<tenant>.sharepoint.com/sites/<name> (or /teams/<name>) URL without query or fragment.'
}
if ($ClientId -eq [guid]::Empty) { throw 'ClientId must be a registered public-client application GUID.' }
$output = [io.path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'OutputDirectory already exists; choose a fresh location.' }
if (-not (Get-Module -ListAvailable -Name PnP.PowerShell)) {
  throw 'PnP.PowerShell is required. Install-Module PnP.PowerShell -Scope CurrentUser'
}
$parent = Split-Path -Parent $output
if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
$stage = Join-Path $parent ('.pnp-staging-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $stage
try {
  # -Interactive requires a tenant-approved app registration; no token or secret is saved by this script.
  $connection = Connect-PnPOnline -Url $site.AbsoluteUri.TrimEnd('/') -ClientId $ClientId -Interactive -ReturnConnection -ErrorAction Stop
  $web = Get-PnPWeb -Includes 'RoleAssignments','Title' -Connection $connection -ErrorAction Stop
  $groupRows = @()
  foreach($grp in @(Get-PnPGroup -Connection $connection -ErrorAction Stop)) {
    foreach($member in @(Get-PnPGroupMember -Group $grp -Connection $connection -ErrorAction Stop)) {
      $groupRows += [pscustomobject]@{
        site_url = $site.AbsoluteUri.TrimEnd('/'); sharepoint_group_id = $grp.Id
        sharepoint_group = $grp.Title; principal_login = $member.LoginName
        principal_email = $member.Email; principal_type = [string]$member.PrincipalType
      }
    }
  }
  $adminRows = @()
  foreach($person in @(Get-PnPSiteCollectionAdmin -Connection $connection -ErrorAction Stop)) {
    $adminRows += [pscustomobject]@{site_url = $site.AbsoluteUri.TrimEnd('/'); principal_login = $person.LoginName;
      principal_email = $person.Email; principal_type = [string]$person.PrincipalType}
  }
  $roleRows = @()
  $null = Get-PnPProperty -ClientObject $web -Property RoleAssignments -Connection $connection -ErrorAction Stop
  foreach($assignment in @($web.RoleAssignments)) {
    $null = Get-PnPProperty -ClientObject $assignment -Property Member,RoleDefinitionBindings -Connection $connection -ErrorAction Stop
    $roles = @($assignment.RoleDefinitionBindings | ForEach-Object { $_.Name })
    $roleRows += [pscustomobject]@{site_url = $site.AbsoluteUri.TrimEnd('/');
      principal_title = $assignment.Member.Title; principal_login = $assignment.Member.LoginName;
      principal_type = [string]$assignment.Member.PrincipalType; role_names = ($roles -join '; ')}
  }
  Export-SafeCsv -Rows $groupRows -Fields @('site_url','sharepoint_group_id','sharepoint_group','principal_login','principal_email','principal_type') -Destination (Join-Path $stage 'sharepoint_group_members.csv')
  Export-SafeCsv -Rows $adminRows -Fields @('site_url','principal_login','principal_email','principal_type') -Destination (Join-Path $stage 'site_collection_admins.csv')
  Export-SafeCsv -Rows $roleRows -Fields @('site_url','principal_title','principal_login','principal_type','role_names') -Destination (Join-Path $stage 'root_web_role_assignments.csv')
  $manifest = [ordered]@{
    schema = 'pnp-sharepoint-v0.3'; source = 'PnP.PowerShell'; site_url = $site.AbsoluteUri.TrimEnd('/');
    collected_at_utc = [datetime]::UtcNow.ToString('o');
    record_counts = @{group_members = @($groupRows).Count; site_collection_admins = @($adminRows).Count;
      root_web_role_assignments = @($roleRows).Count};
    coverage = 'Only the selected site collection, SharePoint group rosters, site collection admins and root-web role assignments.';
    limitations = @('No nested Entra/M365 group expansion','No item/list/subsite inheritance','No anonymous or sharing-link enumeration',
      'No user account status or guest classification','No approval, review-decision, or historical grant-date evidence');
    warning = 'These are direct assignment/group listings, NOT calculated effective permissions or proof of compliance.'
  }
  ($manifest | ConvertTo-Json -Depth 6) | Set-Content -Path (Join-Path $stage 'manifest.json') -Encoding utf8
  Move-Item -LiteralPath $stage -Destination $output -ErrorAction Stop
  Write-Output "Read-only site inventory written to $output"
} finally {
  if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
