"""One-command demo with portable synthetic source files."""
from pathlib import Path
from governance_auditor.__main__ import main

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    raise SystemExit(main(["scan", "--input", str(root / "examples/synthetic"),
                           "--output", str(root / "reports/demo"), "--as-of", "2026-11-04"]))
