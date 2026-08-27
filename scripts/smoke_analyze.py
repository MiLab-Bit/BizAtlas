"""Smoke: load rules + analyze three fixtures without HTTP."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.contracts.models import AnalyzeRequest
from bizatlas.data.db import init_db
from bizatlas.orchestrator.analyze import run_analyze
from bizatlas.rules.engine import load_rules


def main() -> None:
    init_db()
    rules = load_rules()
    print(f"rules_loaded={len(rules)}")
    assert len(rules) >= 20, "need >=20 seed rules"

    for fid in ("healthy", "risky", "defaulted"):
        result = run_analyze(AnalyzeRequest(company_id=fid, intent="analyze_risk"))
        summary = result["summary"]
        print(
            f"{fid}: grade={summary['grade']} score={summary['score']} "
            f"hits={result['rules_hit']} | {summary['headline']}"
        )

    # defaulted should veto to BLACK
    defaulted = run_analyze(AnalyzeRequest(company_id="defaulted"))
    assert defaulted["summary"]["grade"] == "BLACK", defaulted["summary"]
    print("smoke_ok")
    print(json.dumps(defaulted["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
