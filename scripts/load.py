#!/usr/bin/env python3
"""Load the configured dataset into every enabled database and verify it.

    python scripts/load.py

Does not run any performance workloads — see scripts/benchmark.py for that.
Prints per-database load time, throughput, and verification status.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.benchmark.runner import build_adapter, load_config  # noqa: E402
from src.datasets.loader import load_dataset  # noqa: E402


def main():
    databases_config, workloads_config = load_config()
    enabled = [db for db in databases_config if db.get("enabled")]
    if not enabled:
        raise SystemExit("No databases are enabled in config/databases.yaml.")

    dataset = load_dataset(REPO_ROOT / workloads_config["dataset"]["path"])

    for db_config in enabled:
        adapter = build_adapter(db_config)
        adapter.connect()
        try:
            load_stats = adapter.load_data(dataset)
            verification = adapter.verify_data(
                expected_nodes=dataset["node_count"],
                expected_relationships=dataset["relationship_count"],
            )
            status = "OK" if verification["ok"] else "MISMATCH"
            print(f"[{db_config['name']}] {status} — {load_stats} — {verification}")
        finally:
            adapter.close()


if __name__ == "__main__":
    main()
