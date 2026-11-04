"""Generate standalone, safely escaped reports from audit results."""
from __future__ import annotations

import csv
import hashlib
import html
import json
from pathlib import Path

from .engine import Audit


def _csv_safe(value: str) -> str:
    """Neutralize spreadsheet formula injection in exported audit data."""
    value = str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def write_reports(audit: Audit, destination: Path) -> dict[str, Path]:
    destination.mkdir(parents=True, exist_ok=True)
    all_rows = [f.to_dict() for f in audit.findings]
    json_file = destination / "findings.json"
    json_file.write_text(json.dumps(audit.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    csv_file = destination / "findings.csv"
    fields = ["control_id", "severity", "status", "subject", "resource", "title", "detail", "recommendation", "evidence_keys", "exception_reason", "exception_expires"]
    with csv_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in all_rows:
            row = {**row, "evidence_keys": ";".join(row["evidence_keys"])}
            writer.writerow({key: _csv_safe(val) for key, val in row.items()})
    evidence_file = destination / "evidence_correlations.csv"
    with evidence_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["request_id", "user_id", "resource_id", "sailpoint_events", "sentinel_events", "status"])
        writer.writeheader()
        writer.writerows([{k: _csv_safe(v) for k, v in ev.items()} for ev in audit.evidence])
    html_file = destination / "dashboard.html"
    html_file.write_text(render_html(audit), encoding="utf-8")
    # Tamper-evident checksums for the outputs (not an authenticity signature).
    checksum_file = destination / "report_sha256.txt"
    checksum_file.write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in [csv_file, json_file, evidence_file, html_file]), encoding="utf-8")
    return {"dashboard": html_file, "findings_json": json_file, "findings_csv": csv_file,
            "evidence": evidence_file, "checksums": checksum_file}


def render_html(audit: Audit) -> str:
    esc = lambda s: html.escape(str(s), quote=True)
    rows = []
    for f in audit.findings:
        rows.append(
            f'<tr data-severity="{esc(f.severity)}" data-status="{esc(f.status)}">'
            f'<td><span class="mono">{esc(f.control_id)}</span></td>'
            f'<td><span class="tag {esc(f.severity)}">{esc(f.severity).upper()}</span></td>'
            f'<td><span class="status {esc(f.status)}">{esc(f.status).upper()}</span></td>'
            f'<td><strong>{esc(f.title)}</strong><div class="muted small">{esc(f.detail)}</div>'
            f'<div class="recommendation">Next: {esc(f.recommendation)}</div>'
            + (f'<div class="exception">Exception through {esc(f.exception_expires)}: {esc(f.exception_reason)}</div>' if f.status == "excepted" else "")
            + f'</td><td>{esc(f.subject)}</td><td>{esc(f.resource)}</td></tr>')
    c = audit.counts
    stylesheet = """
:root{--ink:#202a36;--muted:#657284;--line:#e5eaf0;--paper:#fff;--bg:#f4f6f9;--navy:#172b42;--bronze:#b58b57}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif;color:var(--ink)}
.top{background:var(--navy);color:white;padding:38px max(26px,calc((100vw - 1160px)/2)) 48px} .eyebrow{font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:#d2b994;font-weight:700}
h1{font-size:31px;line-height:1.2;margin:13px 0 9px;letter-spacing:-.03em}.subtitle{color:#ccd4df;font-size:14px;max-width:700px;line-height:1.6}
.shell{max-width:1160px;margin:-26px auto 50px;padding:0 22px}.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}.metric{background:#fff;border:1px solid var(--line);border-radius:12px;padding:20px 18px;box-shadow:0 2px 12px #172b4209}.metric span{display:block;color:var(--muted);font-size:12px;font-weight:600}.metric b{font-size:28px;display:block;margin-top:4px;color:var(--ink)}
.panel{background:white;border:1px solid var(--line);border-radius:12px;margin-top:20px;overflow:hidden;box-shadow:0 2px 12px #172b4206}.panelhead{padding:24px 25px 17px;display:flex;justify-content:space-between;align-items:center;gap:15px;flex-wrap:wrap}h2{margin:0;font-size:19px;letter-spacing:-.02em}.muted{color:var(--muted)}.small{font-size:12px;line-height:1.5;margin-top:5px}.controls{display:flex;gap:9px;flex-wrap:wrap}input,select{font:inherit;border:1px solid #d6dde7;border-radius:8px;padding:10px 12px;background:white;color:var(--ink)}input{width:220px}table{border-collapse:collapse;width:100%;font-size:13px}th{text-transform:uppercase;letter-spacing:.07em;font-size:10px;background:#f7f9fb;color:#667589;text-align:left;padding:13px 15px;border-top:1px solid var(--line);white-space:nowrap}td{vertical-align:top;border-top:1px solid var(--line);padding:17px 15px;line-height:1.45}td:nth-child(4){min-width:310px}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}.tag,.status{font-size:10px;letter-spacing:.06em;font-weight:750;border-radius:4px;padding:4px 7px;display:inline-block}.high{background:#fcebea;color:#a53532}.medium{background:#fff1d9;color:#92641c}.status.open{color:#334c68;background:#eaf0f8}.status.excepted{color:#476d60;background:#e5f3ea}.recommendation{font-size:12px;margin-top:7px;color:#536780}.exception{color:#47725a;font-size:12px;margin-top:7px}.note{border-left:3px solid var(--bronze);background:#fffbf5;padding:13px 16px;margin-top:20px;border-radius:4px;color:#564c40;font-size:13px;line-height:1.6}.footer{font-size:12px;margin-top:18px;color:var(--muted)}.empty{padding:24px;text-align:center;color:var(--muted)}
@media(max-width:860px){.metrics{grid-template-columns:repeat(2,1fr)}.tablewrap{overflow-x:auto}.top{padding:30px 25px 48px}h1{font-size:25px}}@media print{.top{background:var(--navy)!important;-webkit-print-color-adjust:exact;print-color-adjust:exact}.controls{display:none}.shell{margin:0 auto}.panel{break-inside:avoid}}
"""
    js = """
const search=document.getElementById('search'),sev=document.getElementById('severity'),status=document.getElementById('state');
function filter(){let count=0;for(const r of document.querySelectorAll('#findings tbody tr')){const visible=r.textContent.toLowerCase().includes(search.value.toLowerCase())&&(sev.value==='all'||r.dataset.severity===sev.value)&&(status.value==='all'||r.dataset.status===status.value);r.hidden=!visible;if(visible)count++;}document.getElementById('visible-count').textContent=count+' matching findings';}
search.addEventListener('input',filter);sev.addEventListener('change',filter);status.addEventListener('change',filter);filter();
"""
    return f'''<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Entra &amp; M365 Governance Audit | {esc(audit.as_of)}</title><style>{stylesheet}</style></head>
<body><header class="top"><div class="eyebrow">Identity governance / portfolio demo</div><h1>Entra &amp; Microsoft 365<br>Access Governance Auditor</h1><div class="subtitle">Read-only snapshot assessment • {esc(audit.as_of)} • Synthetic demonstration data. Findings require analyst validation before operational action.</div></header>
<main class="shell"><section class="metrics"><div class="metric"><span>Open findings</span><b>{c['open']}</b></div><div class="metric"><span>High severity</span><b>{c['high']}</b></div><div class="metric"><span>Medium severity</span><b>{c['medium']}</b></div><div class="metric"><span>Approved exceptions</span><b>{c['excepted']}</b></div><div class="metric"><span>Evidence pairs</span><b>{c['correlated_evidence']}</b></div></section>
<div class="note"><strong>Interpretation:</strong> This dashboard checks normalized exports, not live Microsoft 365 tenant policy. Missing events or approvals may reflect incomplete exports. A matched log pair is evidence correlation, not definitive compliance attestation. No access is changed.</div>
<section class="panel"><div class="panelhead"><div><h2>Governance findings</h2><div id="visible-count" class="muted small">{len(rows)} findings</div></div><div class="controls"><input id="search" type="search" aria-label="Search findings" placeholder="Search findings…"><select id="severity" aria-label="Filter severity"><option value="all">All severities</option><option value="high">High</option><option value="medium">Medium</option></select><select id="state" aria-label="Filter status"><option value="all">All statuses</option><option value="open">Open</option><option value="excepted">Excepted</option></select></div></div>
<div class="tablewrap"><table id="findings"><thead><tr><th>Control</th><th>Severity</th><th>Status</th><th>Finding &amp; recommended action</th><th>Subject</th><th>Resource</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>{'<div class="empty">No findings in this snapshot.</div>' if not rows else ''}</section>
<div class="footer">Controls evaluated: {c['controls_evaluated']} | Input files: {len(audit.input_hashes)} | Evidence correlations: {len(audit.evidence)}. See findings.json and report_sha256.txt for traceability.</div></main><script>{js}</script></body></html>'''
