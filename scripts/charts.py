#!/usr/bin/env python3
"""Regenerate charts from an existing raw results file.

    python scripts/charts.py [path/to/benchmark_raw.json]

Defaults to results/raw/benchmark_raw.json.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.benchmark import charts  # noqa: E402


def main():
    raw_path = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "results" / "raw" / "benchmark_raw.json"
    if not raw_path.exists():
        raise SystemExit(f"No raw results at {raw_path}. Run scripts/benchmark.py first.")

    with open(raw_path) as f:
        results = json.load(f)

    written = charts.generate_charts(results, REPO_ROOT / "results" / "charts")
    print(f"Wrote {len(written)} chart(s):")
    for path in written:
        print(f"  - {path}")


if __name__ == "__main__":
    main()
