"""Statistics over raw latency measurements.

Kept dependency-free (no numpy) since it only needs to run on lists of
floats collected during a benchmark session.
"""

import math


def percentile(values, p):
    """Linear-interpolation percentile, matching numpy's default method.

    `values` need not be pre-sorted. `p` is in [0, 100].
    """
    if not values:
        raise ValueError("percentile() requires at least one value")

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (p / 100) * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]

    weight = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def summarize(latencies_ms):
    """Return the standard summary block used throughout results/processed/*.

    `latencies_ms` should contain only successful-request latencies —
    filter out failures before calling this (see latency.py).
    """
    if not latencies_ms:
        return {
            "count": 0,
            "min_ms": None,
            "max_ms": None,
            "mean_ms": None,
            "stdev_ms": None,
            "p50_ms": None,
            "p95_ms": None,
            "p99_ms": None,
        }

    n = len(latencies_ms)
    mean = sum(latencies_ms) / n
    variance = sum((x - mean) ** 2 for x in latencies_ms) / n if n > 1 else 0.0

    return {
        "count": n,
        "min_ms": min(latencies_ms),
        "max_ms": max(latencies_ms),
        "mean_ms": mean,
        "stdev_ms": math.sqrt(variance),
        "p50_ms": percentile(latencies_ms, 50),
        "p95_ms": percentile(latencies_ms, 95),
        "p99_ms": percentile(latencies_ms, 99),
    }


def error_rate(total_operations, failed_operations):
    if total_operations == 0:
        return 0.0
    return (failed_operations / total_operations) * 100
