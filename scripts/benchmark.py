#!/usr/bin/env python3
"""One-command benchmark execution.

    python scripts/benchmark.py

Runs the full flow (load -> verify -> warm up -> execute workloads ->
measure -> summarize) for every enabled database and writes
results/raw/benchmark_raw.json. Generating processed CSV/summary and
charts from that file is a separate step (not yet implemented — see
README section 38).
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.benchmark.runner import main  # noqa: E402

if __name__ == "__main__":
    main()
