"""Concurrent mixed read/write workload runner.

Uses a thread pool because graph database drivers are typically blocking
I/O (network calls), so threads give real concurrency without requiring
every adapter to be async.
"""

import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .metrics import error_rate, summarize


def _run_one_operation(read_fn, write_fn, read_percentage):
    is_read = random.uniform(0, 100) < read_percentage
    start = time.perf_counter()
    error = None
    try:
        (read_fn if is_read else write_fn)()
    except Exception as exc:  # noqa: BLE001 - recorded as a failed op, not raised
        error = str(exc)
    latency_ms = (time.perf_counter() - start) * 1000
    return {
        "op_type": "read" if is_read else "write",
        "latency_ms": latency_ms,
        "success": error is None,
        "error": error,
    }


def run_mixed_workload(read_fn, write_fn, concurrency, duration_seconds, read_percentage):
    """Run `read_fn`/`write_fn` concurrently for `duration_seconds`.

    Each worker thread issues operations back-to-back (closed-loop) until
    the deadline passes. Returns a summary dict with throughput, error
    rate, and latency percentiles alongside the raw per-operation records.
    """
    deadline = time.perf_counter() + duration_seconds
    results = []

    def worker_loop():
        local_results = []
        while time.perf_counter() < deadline:
            local_results.append(_run_one_operation(read_fn, write_fn, read_percentage))
        return local_results

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(worker_loop) for _ in range(concurrency)]
        for future in as_completed(futures):
            results.extend(future.result())
    wall_clock_seconds = time.perf_counter() - start

    total = len(results)
    failed = sum(1 for r in results if not r["success"])
    successful_latencies = [r["latency_ms"] for r in results if r["success"]]

    return {
        "concurrency": concurrency,
        "read_percentage": read_percentage,
        "write_percentage": 100 - read_percentage,
        "duration_seconds": wall_clock_seconds,
        "total_operations": total,
        "successful_operations": total - failed,
        "failed_operations": failed,
        "throughput_ops_per_sec": total / wall_clock_seconds if wall_clock_seconds else 0.0,
        "error_rate_pct": error_rate(total, failed),
        **summarize(successful_latencies),
        "raw": results,
    }
