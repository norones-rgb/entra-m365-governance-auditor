"""Offline synthetic scorecard demonstration, pinned to a reproducible date."""
from __future__ import annotations
import datetime as dt
import json
import shutil
from pathlib import Path
from governance_auditor.scorecard import create_scorecard

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / 'examples' / 'governance_demo_output'
OUTPUT = ROOT / 'reports' / 'scorecard-demo'
AS_OF = dt.datetime(2026, 11, 15, 12, 0, tzinfo=dt.timezone.utc)


def run() -> dict:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)  # Known generated demo directory only
    report = create_scorecard(PACKAGE, OUTPUT, AS_OF)
    print(json.dumps({"readiness":report["readiness"],"counts":report["counts"],"output":str(OUTPUT)},indent=2))
    return report

if __name__ == '__main__':
    run()