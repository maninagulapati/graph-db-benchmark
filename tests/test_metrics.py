import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.benchmark.metrics import error_rate, percentile, summarize


def test_percentile_p50_of_odd_length():
    assert percentile([1, 2, 3], 50) == 2


def test_percentile_p95_matches_known_value():
    values = list(range(1, 101))  # 1..100
    assert percentile(values, 95) == 95.05


def test_percentile_single_value():
    assert percentile([42], 50) == 42
    assert percentile([42], 95) == 42


def test_summarize_empty():
    result = summarize([])
    assert result["count"] == 0
    assert result["p50_ms"] is None


def test_summarize_basic():
    result = summarize([10, 20, 30, 40, 50])
    assert result["count"] == 5
    assert result["min_ms"] == 10
    assert result["max_ms"] == 50
    assert result["mean_ms"] == 30
    assert result["p50_ms"] == 30


def test_error_rate():
    assert error_rate(100, 5) == 5.0
    assert error_rate(0, 0) == 0.0
