"""Build a deterministic, fully fabricated SharePoint / Entra reconciliation report."""
from pathlib import Path
from governance_auditor.reconcile import reconcile

HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    summary = reconcile(HERE / "examples/reconciliation_synthetic/graph",
                        HERE / "examples/reconciliation_synthetic/sharepoint",
                        HERE / "reports/reconciliation-demo")
    print("Reconciliation demo:", summary["observation_count"], "observations",
          summary["resolution_counts"], "disabled:", summary["disabled_account_review_indicators"])