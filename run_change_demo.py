"""Run synthetic comparison; no authentication, network, or external packages."""
from pathlib import Path
from governance_auditor.snapshot_diff import compare_snapshots

ROOT = Path(__file__).resolve().parent
if __name__ == '__main__':
    sample = ROOT / 'examples' / 'change_synthetic'
    output = ROOT / 'reports' / 'change-demo'
    if output.exists():
        raise SystemExit(f'Report directory exists: {output}. Remove only generated reports before rerunning.')
    summary = compare_snapshots(sample/'before'/'graph', sample/'after'/'graph', output,
                                sample/'before'/'sharepoint', sample/'after'/'sharepoint')
    print(f"Changes: {summary['changes']}; non-comparable scopes: {summary['non_comparable_scopes']}")
    print(output / 'dashboard.html')
