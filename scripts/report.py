#!/usr/bin/env python3
"""Regenerate processed results from an existing raw results file.

    python scripts/report.py [path/to/benchmark_raw.json]

Defaults to results/raw/benchmark_raw.json. Useful for recomputing
summaries/anomaly detection without re-running the benchmark — the raw
file retains every individual measurement (README section 36).
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.benchmark import report  # noqa: E402


def main():
    raw_path = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "results" / "raw" / "benchmark_raw.json"
    if not raw_path.exists():
        raise SystemExit(f"No raw results at {raw_path}. Run scripts/benchmark.py first.")

    with open(raw_path) as f:
        results = json.load(f)

    stats = report.save_processed(results, REPO_ROOT / "results" / "processed")
    print(f"Wrote {stats['summary_rows']} summary row(s); flagged {stats['anomalies']} anomaly/anomalies.")


if __name__ == "__main__":
    main()
