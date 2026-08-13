#!/usr/bin/env python3
"""Validate configuration and credentials before running the benchmark.

    python scripts/setup.py

Checks:
  - config/databases.yaml and config/workloads.yaml parse and have the
    required keys
  - every enabled database has its credential env vars set (via .env)
  - the configured dataset file exists

Does not connect to any database — connectivity is exercised by
`python scripts/load.py`.
"""

import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def main():
    load_dotenv(REPO_ROOT / ".env")
    problems = []

    with open(REPO_ROOT / "config" / "databases.yaml") as f:
        databases = yaml.safe_load(f)["databases"]
    with open(REPO_ROOT / "config" / "workloads.yaml") as f:
        workloads = yaml.safe_load(f)

    enabled = [db for db in databases if db.get("enabled")]
    if not enabled:
        problems.append("No databases are enabled in config/databases.yaml.")

    for db in enabled:
        missing = [var for var in db.get("credentials_env", []) if not os.getenv(var)]
        if missing:
            problems.append(f"{db['name']}: missing environment variables {missing}")

    dataset_path = REPO_ROOT / workloads["dataset"]["path"]
    if not dataset_path.exists():
        problems.append(
            f"Dataset file not found at {dataset_path}. "
            "Run `python -m src.datasets.generator` for a smoke-test dataset, "
            "or place a real dataset there (see data/README.md)."
        )

    if problems:
        print("Setup check failed:")
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(1)

    print(f"Setup check passed. {len(enabled)} database(s) enabled: "
          f"{', '.join(db['name'] for db in enabled)}")


if __name__ == "__main__":
    main()
