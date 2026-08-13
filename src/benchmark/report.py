"""Turn raw benchmark results into the processed outputs described in the
project README: a flat summary table, the full results matrix, and a
variance/anomaly list.

Takes the in-memory list of per-database dicts produced by
runner.run_benchmark_for_database (the same shape written to
results/raw/benchmark_raw.json), so it can be re-run standalone against a
saved raw file without re-executing the benchmark — see scripts/report.py.
"""

import csv
import json
from pathlib import Path

from .metrics import percentile

WORKLOADS = ["point_lookup", "indexed_lookup", "traversal_1hop", "traversal_2hop", "traversal_3hop", "aggregation"]

# A measurement more than this many multiples of the workload's own p50
# above that p50 is flagged for investigation, not discarded — see README
# section "Variance Analysis": unexpected results should be recorded, not
# silently dropped.
ANOMALY_MULTIPLE_OF_P50 = 10


def build_processed_summary(results):
    """One row per (database, workload) with the standard percentile block."""
    rows = []
    for db_result in results:
        for workload, stats in db_result["summary"].items():
            rows.append({"database": db_result["database"], "workload": workload, **stats})
    return rows


def build_results_matrix(results):
    """The nested structure backing the README's per-category results tables."""
    matrix = {"loading": {}, "lookups": {}, "traversals": {}, "aggregation": {}, "mixed_workload": {}, "resources": {}}

    for db_result in results:
        name = db_result["database"]
        matrix["loading"][name] = db_result["load_stats"]
        matrix["lookups"][name] = {
            "point": db_result["summary"].get("point_lookup"),
            "indexed": db_result["summary"].get("indexed_lookup"),
        }
        matrix["traversals"][name] = {
            "1hop": db_result["summary"].get("traversal_1hop"),
            "2hop": db_result["summary"].get("traversal_2hop"),
            "3hop": db_result["summary"].get("traversal_3hop"),
        }
        matrix["aggregation"][name] = db_result["summary"].get("aggregation")
        matrix["mixed_workload"][name] = db_result["mixed_workload"]
        matrix["resources"][name] = {
            "configured": db_result.get("resources", {}),
            "observed": db_result.get("resource_footprint", {"observable": False}),
        }

    return matrix


def build_cold_vs_warm_table(results):
    """Rows matching the README's Cold vs Warm Analysis table."""
    rows = []
    for db_result in results:
        for workload, comparison in db_result.get("cold_vs_warm", {}).items():
            rows.append({
                "database": db_result["database"],
                "workload": workload,
                "cold_p50_ms": comparison["cold"]["p50_ms"],
                "warm_p50_ms": comparison["warm"]["p50_ms"],
                "cold_p95_ms": comparison["cold"]["p95_ms"],
                "warm_p95_ms": comparison["warm"]["p95_ms"],
            })
    return rows


def detect_anomalies(results, multiple_of_p50=ANOMALY_MULTIPLE_OF_P50):
    """Flag individual measurements far above their own workload's p50.

    Returns the raw records rather than a count — an anomaly is data to
    investigate (see README "Variance Analysis"), not something to
    average away.
    """
    anomalies = []
    for db_result in results:
        records = db_result["raw_latency_records"]
        by_workload = {}
        for record in records:
            if record["success"] and record["phase"] == "benchmark":
                by_workload.setdefault(record["workload"], []).append(record["latency_ms"])

        thresholds = {
            workload: percentile(latencies, 50) * multiple_of_p50
            for workload, latencies in by_workload.items()
            if latencies
        }

        for record in records:
            threshold = thresholds.get(record["workload"])
            if threshold is not None and record["latency_ms"] > threshold:
                anomalies.append({**record, "database": db_result["database"], "threshold_ms": threshold})

    return anomalies


def save_processed(results, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_rows = build_processed_summary(results)
    if summary_rows:
        with open(output_dir / "benchmark_summary.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
            writer.writeheader()
            writer.writerows(summary_rows)

    with open(output_dir / "benchmark_summary.json", "w") as f:
        json.dump(summary_rows, f, indent=2)

    with open(output_dir / "results_matrix.json", "w") as f:
        json.dump(build_results_matrix(results), f, indent=2)

    cold_vs_warm_rows = build_cold_vs_warm_table(results)
    with open(output_dir / "cold_vs_warm.json", "w") as f:
        json.dump(cold_vs_warm_rows, f, indent=2)

    anomalies = detect_anomalies(results)
    with open(output_dir / "anomalies.json", "w") as f:
        json.dump(anomalies, f, indent=2)

    return {
        "summary_rows": len(summary_rows),
        "anomalies": len(anomalies),
    }
