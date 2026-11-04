# Control rationale and analyst guidance

| Control | Source signal | What to verify manually |
|---|---|---|
| PRV-001 | Privileged membership and missing **current** approved request | Check emergency access, grandfathered access, migration, expired approvals and export coverage. |
| PRV-002 | Membership grant date earlier than approval | Was access temporarily approved through an emergency path or was a timestamp normalized incorrectly? |
| PRV-003 | Disabled user with privileged membership | Is the membership effective? Is account disabled in the authoritative directory? |
| PRV-004 | No owner in group snapshot | Does the directory store an owner outside the selected export? |
| SP-001 | Sensitive site guest with no current site approval | Check an external-sharing sponsor, B2B approval, and permission inheritance. |
| SP-002 | No site owner | Review Microsoft 365/SharePoint site ownership and site lifecycle state. |
| SP-003 | Disabled user with direct exported site permission | Determine if permission has any effective impact and whether offboarding is complete. |
| REV-001 | Campaign not closed after its due date | Check IGA campaign state, reassignment, extensions and control owner signoff. |
| AUD-001 | Incomplete pair of IGA/SIEM audit events | First confirm log retention, connector coverage, event naming, request-ID mapping and ingestion health. |

**No auto-remediation:** A finding is a request for investigation. Do not delete group members, block access, or change policies based solely on a CSV finding.

## Rule scope and false positives

`PRV-001` uses current approvals as of the evaluation date, not a historical approval-at-grant completeness check. `SP-001` is intentionally limited to guests on explicitly sensitive sites. `AUD-001` is a demonstration of a correlation strategy from an identity governance team; neither SIEM nor IGA universally emits these exact event names or IDs. These assumptions need tuning with a service owner before applying to enterprise records.
