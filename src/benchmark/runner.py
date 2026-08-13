"""Benchmark orchestrator.

Ties together config, adapters, latency capture, and concurrency testing
into the execution flow described in the project README:

    load config -> connect -> load dataset -> verify -> warm up
    -> execute workloads -> collect measurements -> summarize -> save

Run via `python -m benchmark.run` (see scripts/benchmark.py) once at least
one database in config/databases.yaml has `enabled: true` and a real
adapter implementation.
"""

import importlib
import json
import os
import random
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .concurrency import run_mixed_workload
from .latency import LatencyRecorder
from .metrics import summarize

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_config():
    load_dotenv(REPO_ROOT / ".env")
    with open(REPO_ROOT / "config" / "databases.yaml") as f:
        databases_config = yaml.safe_load(f)["databases"]
    with open(REPO_ROOT / "config" / "workloads.yaml") as f:
        workloads_config = yaml.safe_load(f)
    return databases_config, workloads_config


def build_adapter(db_config):
    """Import and instantiate the adapter named in a database's config entry."""
    module_name, class_name = db_config["adapter"].split(":")
    module = importlib.import_module(f"src.adapters.{module_name}")
    adapter_cls = getattr(module, class_name)

    missing = [var for var in db_config.get("credentials_env", []) if not os.getenv(var)]
    if missing:
        raise RuntimeError(
            f"{db_config['name']}: missing environment variables {missing}. "
            "Set them in .env (see .env.example)."
        )

    return adapter_cls(db_config["name"], db_config)


WARM_UP_OPERATIONS = ["point_lookup", "traversal_1hop", "traversal_2hop", "traversal_3hop"]


def _measure(recorder, database, workload, iteration, operation, phase="benchmark"):
    """Run `operation()` under recorder.measure(), then swallow any exception.

    recorder.measure()'s own `finally` block has already recorded the
    failure (success=False, error=str(exc)) by the time it re-raises — a
    single query failing (e.g. a free-tier instance's connection dying
    under a resource-heavy 3-hop traversal) should not abort the rest of
    the benchmark run for every other workload and iteration.
    """
    try:
        with recorder.measure(database, workload, iteration, phase=phase):
            operation()
    except Exception:
        pass


def warm_up(adapter, recorder, workload_config, sample_node_ids, rng):
    """Execute and discard warm-up queries so caches/plans are hot before measuring.

    Warm-up latencies are recorded under phase="warmup" using the same
    workload names as the benchmark phase, so they can later be compared
    directly as "cold" vs "warm" measurements (see report.py:
    build_cold_vs_warm) instead of being thrown away.
    """
    iterations = workload_config["warmup"]["iterations"]
    for i in range(iterations):
        node_id = rng.choice(sample_node_ids)
        for workload_name in WARM_UP_OPERATIONS:
            operation = getattr(adapter, workload_name)
            _measure(recorder, adapter.name, workload_name, i, lambda op=operation: op(node_id), phase="warmup")


def run_read_workload(adapter, recorder, workload_name, operation, iterations, sample_node_ids, rng):
    for i in range(iterations):
        node_id = rng.choice(sample_node_ids)
        _measure(recorder, adapter.name, workload_name, i, lambda: operation(node_id))


def run_benchmark_for_database(db_config, workloads_config, sample_node_ids, dataset):
    recorder = LatencyRecorder()
    adapter = build_adapter(db_config)
    adapter.connect()

    # Fresh Random(seed) per database, seeded identically — every enabled
    # database walks the exact same sequence of "random" starting nodes in
    # the sequential workloads below (README "Randomized Starting Nodes").
    rng = random.Random(workloads_config["random_seed"])

    try:
        load_stats = adapter.load_data(dataset)
        verification = adapter.verify_data(
            expected_nodes=dataset["node_count"],
            expected_relationships=dataset["relationship_count"],
        )
        if not verification["ok"]:
            raise RuntimeError(
                f"{db_config['name']}: dataset verification failed — "
                f"expected {dataset['node_count']} nodes / "
                f"{dataset['relationship_count']} relationships, got "
                f"{verification['actual_nodes']} / {verification['actual_relationships']}"
            )

        warm_up(adapter, recorder, workloads_config, sample_node_ids, rng)

        iterations = workloads_config["benchmark"]["iterations"]
        run_read_workload(adapter, recorder, "point_lookup", adapter.point_lookup, iterations, sample_node_ids, rng)
        run_read_workload(adapter, recorder, "traversal_1hop", adapter.traversal_1hop, iterations, sample_node_ids, rng)
        run_read_workload(adapter, recorder, "traversal_2hop", adapter.traversal_2hop, iterations, sample_node_ids, rng)
        run_read_workload(adapter, recorder, "traversal_3hop", adapter.traversal_3hop, iterations, sample_node_ids, rng)

        indexed_property = workloads_config["lookups"]["indexed"]["property"]
        for i in range(iterations):
            value = rng.choice(dataset["sample_values"][indexed_property])
            _measure(recorder, adapter.name, "indexed_lookup", i, lambda v=value: adapter.indexed_lookup(indexed_property, v))

        group_by = workloads_config["aggregation"]["group_by"]
        for i in range(iterations):
            _measure(recorder, adapter.name, "aggregation", i, lambda: adapter.aggregation(group_by))

        # Uses the global `random` module here, not `rng` — concurrent
        # worker threads would race on a single Random instance's mutable
        # state, and exact reproducibility isn't the goal for this
        # workload the way it is for the sequential ones above.
        mixed_config = workloads_config["mixed_workload"]
        mixed_results = [
            run_mixed_workload(
                read_fn=lambda: adapter.point_lookup(random.choice(sample_node_ids)),
                write_fn=lambda: adapter.write(dataset["sample_write_payload"]),
                concurrency=level,
                duration_seconds=mixed_config["duration_seconds"],
                read_percentage=mixed_config["read_percentage"],
            )
            for level in mixed_config["concurrency_levels"]
        ]

        summarized_workloads = ["point_lookup", "traversal_1hop", "traversal_2hop", "traversal_3hop", "indexed_lookup", "aggregation"]
        return {
            "database": db_config["name"],
            "resources": db_config.get("resources", {}),
            "resource_footprint": adapter.resource_footprint(),
            "load_stats": load_stats,
            "verification": verification,
            "raw_latency_records": recorder.records,
            "summary": {
                workload: summarize(recorder.successful_latencies(adapter.name, workload))
                for workload in summarized_workloads
            },
            "cold_vs_warm": {
                workload: {
                    "cold": summarize(recorder.successful_latencies(adapter.name, workload, phase="warmup")),
                    "warm": summarize(recorder.successful_latencies(adapter.name, workload, phase="benchmark")),
                }
                for workload in WARM_UP_OPERATIONS
            },
            "mixed_workload": mixed_results,
        }
    finally:
        adapter.close()


def _empty_result_with_error(name, error):
    """Placeholder result when a database's entire run fails (not just one
    query) — e.g. connect()/load_data()/verify_data() itself raising. Keeps
    the same shape report.py/charts.py expect so one database's fatal
    failure doesn't also prevent every other database from being reported.
    """
    return {
        "database": name,
        "resources": {},
        "resource_footprint": {"observable": False},
        "load_stats": {},
        "verification": {"ok": False, "actual_nodes": None, "actual_relationships": None},
        "raw_latency_records": [],
        "summary": {},
        "cold_vs_warm": {},
        "mixed_workload": [],
        "fatal_error": error,
    }


def main():
    databases_config, workloads_config = load_config()
    enabled = [db for db in databases_config if db.get("enabled")]
    if not enabled:
        raise SystemExit(
            "No databases are enabled in config/databases.yaml. "
            "Set `enabled: true` on at least one entry with a real adapter."
        )

    with open(REPO_ROOT / workloads_config["dataset"]["path"]) as f:
        dataset = json.load(f)
    sample_node_ids = dataset["sample_node_ids"]

    results = []
    for db_config in enabled:
        try:
            results.append(run_benchmark_for_database(db_config, workloads_config, sample_node_ids, dataset))
        except Exception as exc:
            print(f"WARNING: {db_config['name']} failed entirely — {exc}")
            results.append(_empty_result_with_error(db_config["name"], str(exc)))

    from .environment import capture_environment

    output_path = REPO_ROOT / "results" / "raw" / "benchmark_raw.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Wrote raw results for {len(results)} database(s) to {output_path}")

    environment_path = REPO_ROOT / "results" / "raw" / "environment.json"
    with open(environment_path, "w") as f:
        json.dump(capture_environment(), f, indent=2)
    print(f"Wrote client environment info to {environment_path}")

    from . import report  # deferred: only needed when actually running the benchmark

    processed_stats = report.save_processed(results, REPO_ROOT / "results" / "processed")
    print(f"Wrote processed summary to {REPO_ROOT / 'results' / 'processed'}")
    if processed_stats["anomalies"]:
        print(f"Flagged {processed_stats['anomalies']} anomalous latency measurement(s) — see processed summary for detail.")

    from . import charts

    chart_paths = charts.generate_charts(results, REPO_ROOT / "results" / "charts")
    print(f"Wrote {len(chart_paths)} chart(s) to {REPO_ROOT / 'results' / 'charts'}")


if __name__ == "__main__":
    main()
