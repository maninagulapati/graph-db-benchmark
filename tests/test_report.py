import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.benchmark import report


def _fake_result(database):
    records = [
        {"database": database, "workload": "point_lookup", "phase": "benchmark", "iteration": i,
         "latency_ms": 2.0 + i * 0.1, "success": True, "error": None}
        for i in range(10)
    ]
    # one clear outlier, far above the workload's own p50
    records.append({"database": database, "workload": "point_lookup", "phase": "benchmark",
                     "iteration": 99, "latency_ms": 500.0, "success": True, "error": None})

    return {
        "database": database,
        "resources": {"vcpu": 2, "ram_gb": 4},
        "resource_footprint": {"observable": False},
        "load_stats": {"nodes_per_second": 1000, "relationships_per_second": 2000},
        "verification": {"ok": True, "actual_nodes": 100, "actual_relationships": 200},
        "raw_latency_records": records,
        "summary": {
            "point_lookup": {"count": 11, "p50_ms": 2.4, "p95_ms": 2.9, "p99_ms": 500.0,
                              "min_ms": 2.0, "max_ms": 500.0, "mean_ms": 47.0, "stdev_ms": 100.0},
            "indexed_lookup": {"count": 10, "p50_ms": 3.0, "p95_ms": 4.0, "p99_ms": 4.5,
                                "min_ms": 2.5, "max_ms": 4.5, "mean_ms": 3.1, "stdev_ms": 0.5},
        },
        "cold_vs_warm": {
            "point_lookup": {
                "cold": {"p50_ms": 5.0, "p95_ms": 6.0},
                "warm": {"p50_ms": 2.4, "p95_ms": 2.9},
            },
        },
        "mixed_workload": [
            {"concurrency": 1, "throughput_ops_per_sec": 100.0, "p95_ms": 5.0, "error_rate_pct": 0.0},
            {"concurrency": 10, "throughput_ops_per_sec": 800.0, "p95_ms": 12.0, "error_rate_pct": 1.0},
        ],
    }


def test_build_processed_summary_has_one_row_per_workload():
    results = [_fake_result("database_a")]
    rows = report.build_processed_summary(results)
    assert len(rows) == 2
    assert {r["workload"] for r in rows} == {"point_lookup", "indexed_lookup"}


def test_build_results_matrix_shape():
    results = [_fake_result("database_a"), _fake_result("database_b")]
    matrix = report.build_results_matrix(results)
    assert set(matrix["loading"].keys()) == {"database_a", "database_b"}
    assert matrix["traversals"]["database_a"]["1hop"] is None


def test_build_cold_vs_warm_table():
    rows = report.build_cold_vs_warm_table([_fake_result("database_a")])
    assert rows == [{
        "database": "database_a", "workload": "point_lookup",
        "cold_p50_ms": 5.0, "warm_p50_ms": 2.4, "cold_p95_ms": 6.0, "warm_p95_ms": 2.9,
    }]


def test_detect_anomalies_flags_outlier_not_the_normal_points():
    anomalies = report.detect_anomalies([_fake_result("database_a")])
    assert len(anomalies) == 1
    assert anomalies[0]["latency_ms"] == 500.0


def test_save_processed_writes_expected_files():
    results = [_fake_result("database_a")]
    with tempfile.TemporaryDirectory() as tmp:
        stats = report.save_processed(results, tmp)
        assert stats == {"summary_rows": 2, "anomalies": 1}

        out = Path(tmp)
        assert (out / "benchmark_summary.csv").exists()
        assert (out / "benchmark_summary.json").exists()
        assert (out / "results_matrix.json").exists()
        assert (out / "cold_vs_warm.json").exists()
        assert (out / "anomalies.json").exists()

        with open(out / "anomalies.json") as f:
            assert len(json.load(f)) == 1
