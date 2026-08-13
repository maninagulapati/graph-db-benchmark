"""Raw latency capture.

Every individual query execution is recorded as its own record — never
pre-averaged — so percentiles and failure analysis can be computed (and
recomputed) later from results/raw/*.
"""

import json
import time
from contextlib import contextmanager


class LatencyRecorder:
    def __init__(self):
        self.records = []

    @contextmanager
    def measure(self, database, workload, iteration, phase="benchmark"):
        """Time one operation and record it, including on failure.

        Usage:
            with recorder.measure("database_a", "point_lookup", i):
                adapter.point_lookup(node_id)
        """
        start = time.perf_counter()
        error = None
        try:
            yield
        except Exception as exc:  # noqa: BLE001 - failures are data, not bugs to swallow
            error = str(exc)
            raise
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            self.records.append({
                "database": database,
                "workload": workload,
                "phase": phase,
                "iteration": iteration,
                "latency_ms": latency_ms,
                "success": error is None,
                "error": error,
            })

    def successful_latencies(self, database=None, workload=None, phase="benchmark"):
        return [
            r["latency_ms"] for r in self.records
            if r["success"]
            and (database is None or r["database"] == database)
            and (workload is None or r["workload"] == workload)
            and r["phase"] == phase
        ]

    def failures(self, database=None, workload=None):
        return [
            r for r in self.records
            if not r["success"]
            and (database is None or r["database"] == database)
            and (workload is None or r["workload"] == workload)
        ]

    def to_json(self, path):
        with open(path, "w") as f:
            json.dump(self.records, f, indent=2)
