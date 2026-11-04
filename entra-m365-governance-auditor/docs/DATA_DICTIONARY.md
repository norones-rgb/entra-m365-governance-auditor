# Normalized data dictionary

Each file must be UTF-8 CSV with a header. Column order may vary, but all required columns must exist. Unknown extra columns are ignored. ISO dates are `YYYY-MM-DD` (the first ten characters of an ISO timestamp are also accepted). Empty CSVs are valid only if they include their header row.

| File | Required columns | Interpretation |
|---|---|---|
| `users.csv` | `user_id,display_name,user_type,enabled,job_role` | `user_type` is Member/Guest/External. `enabled` is true/false. |
| `groups.csv` | `group_id,name,privileged,owner_id` | Privilege must be explicitly classified as true/false; blank owner allowed. |
| `memberships.csv` | `group_id,user_id,granted_at` | One direct user-to-group membership per row. |
| `approvals.csv` | `request_id,user_id,resource_type,resource_id,status,approved_at,expires_at` | `resource_type` is `group` or `site`, `status=approved` is used. Blank `expires_at` = no expiry in source; consider local policy. |
| `sites.csv` | `site_id,name,sensitivity,owner_id` | Sensitive categories are `restricted` and `confidential`; blank owner allowed. |
| `site_permissions.csv` | `site_id,user_id,permission,granted_at` | Direct, flattened SharePoint user permission. |
| `campaigns.csv` | `campaign_id,type,resource_id,owner_id,due_date,status` | `completed` and `closed` are treated as finished; any other status due before as-of is overdue. |
| `audit_events.csv` | `event_id,source,request_id,user_id,resource_id,event_type,occurred_at` | `source` SailPoint/Sentinel, event types `approval_recorded`/`membership_change` for example correlation. |
| `exceptions.csv` | `control_id,subject,expires_on,approved_by,reason` | Exact matching of rule and finding subject; expired exceptions not honored. |

The synthetic data uses stable **fictional** IDs rather than any real company's directory identifiers. Refer to `examples/synthetic` for precise values and formats.

## Output contract

- `findings.json`: full finding list, source-file hashes, counts, snapshot date, and evidence correlations.
- `findings.csv`: one row per identified control issue, with status `open` or `excepted`.
- `evidence_correlations.csv`: request IDs and the corresponding **event IDs** for valid approval/event pairs, never raw security logs.
- `dashboard.html`: fully self-contained visualization, usable offline.
- `report_sha256.txt`: SHA-256 checksums of generated outputs. It detects changes if the file and manifest are independently retained; it is not an authenticity signature.

## Known limitations

- There is no central clock tolerance, time zone normalization, or event ingestion validation in v0.1.
- Events are checked for matching identifiers/type, not complete provenance or historical sequence.
- Duplicate memberships/site grants are not normalized; source extractors should de-duplicate these records.
- The tool does not confirm that an approval is tied to the specific original grant event beyond matching identity/resource IDs.
- Owner references and campaign statuses are based on source data, not live directory resolution.
