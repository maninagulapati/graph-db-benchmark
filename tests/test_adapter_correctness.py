"""Query-correctness tests against a small, hand-verifiable fixture graph.

README section 30 ("Query Result Validation") wants correctness checked
separately from performance. This runs against the Kuzu adapter
specifically — it's embedded and needs no live credentials or network
access, so it can run offline and in CI, unlike the CognoDB adapter.
Every adapter implements the same logical operations (see queries/*.py),
so verifying one adapter's Cypher against known-correct answers is a real
check on the query logic itself, not just on Kuzu.

Fixture graph (directed FRIENDS_WITH edges):

    0 -> 1 -> 2 -> 3 -> 4
              1 -------> 3

Countries: 0=US, 1=US, 2=GB, 3=GB, 4=DE
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.adapters.kuzu_adapter import KuzuAdapter

COUNTRIES = {0: "US", 1: "US", 2: "GB", 3: "GB", 4: "DE"}
EDGES = [(0, 1), (1, 2), (2, 3), (3, 4), (1, 3)]


def _fixture_dataset():
    nodes = [
        {"id": i, "name": f"user-{i}", "age": 20 + i, "country": COUNTRIES[i], "category": "standard"}
        for i in range(5)
    ]
    relationships = [{"source": s, "target": t, "type": "FRIENDS_WITH"} for s, t in EDGES]
    return {
        "node_count": len(nodes),
        "relationship_count": len(relationships),
        "nodes": nodes,
        "relationships": relationships,
        "sample_node_ids": [0, 1, 2, 3, 4],
        "sample_values": {"country": ["US", "GB", "DE"]},
        "sample_write_payload": {"id": 999, "name": "user-999", "age": 30, "country": "US", "category": "standard"},
    }


def _loaded_adapter(tmp_path):
    adapter = KuzuAdapter("kuzu-test", {"db_path": str(tmp_path / "kuzu_test_db")})
    adapter.connect()
    dataset = _fixture_dataset()
    adapter.load_data(dataset)
    return adapter


def test_point_lookup_returns_exactly_one_node(tmp_path):
    adapter = _loaded_adapter(tmp_path)
    try:
        result = adapter.point_lookup(2)
        assert result is not None
        row = result[0] if isinstance(result, list) else result
        assert row["id"] == 2
        assert row["name"] == "user-2"
    finally:
        adapter.close()


def test_point_lookup_missing_id_returns_none(tmp_path):
    adapter = _loaded_adapter(tmp_path)
    try:
        assert adapter.point_lookup(9999) is None
    finally:
        adapter.close()


def test_1hop_matches_expected_neighbor_set(tmp_path):
    adapter = _loaded_adapter(tmp_path)
    try:
        neighbor_ids = {row[0]["id"] for row in adapter.traversal_1hop(0)}
        assert neighbor_ids == {1}

        neighbor_ids = {row[0]["id"] for row in adapter.traversal_1hop(1)}
        assert neighbor_ids == {2, 3}
    finally:
        adapter.close()


def test_2hop_matches_expected_neighbor_set(tmp_path):
    adapter = _loaded_adapter(tmp_path)
    try:
        # 0 -> 1 -> {2, 3}
        neighbor_ids = {row[0]["id"] for row in adapter.traversal_2hop(0)}
        assert neighbor_ids == {2, 3}
    finally:
        adapter.close()


def test_3hop_matches_expected_neighbor_set(tmp_path):
    adapter = _loaded_adapter(tmp_path)
    try:
        # Exactly-length-3 paths from 0: 0-1-2-3 and 0-1-3-4
        neighbor_ids = {row[0]["id"] for row in adapter.traversal_3hop(0)}
        assert neighbor_ids == {3, 4}
    finally:
        adapter.close()


def test_indexed_lookup_matches_expected_group(tmp_path):
    adapter = _loaded_adapter(tmp_path)
    try:
        us_users = {row[0]["id"] for row in adapter.indexed_lookup("country", "US")}
        assert us_users == {0, 1}
    finally:
        adapter.close()


def test_aggregation_matches_expected_counts(tmp_path):
    adapter = _loaded_adapter(tmp_path)
    try:
        counts = {row[0]: row[1] for row in adapter.aggregation("country")}
        assert counts == {"US": 2, "GB": 2, "DE": 1}
    finally:
        adapter.close()


def test_verify_data_detects_correct_load(tmp_path):
    adapter = _loaded_adapter(tmp_path)
    try:
        result = adapter.verify_data(expected_nodes=5, expected_relationships=5)
        assert result == {"ok": True, "actual_nodes": 5, "actual_relationships": 5}
    finally:
        adapter.close()


def test_verify_data_flags_mismatch(tmp_path):
    adapter = _loaded_adapter(tmp_path)
    try:
        result = adapter.verify_data(expected_nodes=999, expected_relationships=999)
        assert result["ok"] is False
    finally:
        adapter.close()
