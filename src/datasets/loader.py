"""Load a normalized dataset file shared by every adapter.

The benchmark works from one JSON representation so that "same dataset
across platforms" (README section 4) is enforced by construction rather
than by convention: every adapter's load_data() receives this exact
structure and is responsible for writing it into its own database using
whatever import mechanism that platform prefers.

Expected shape:
    {
      "node_count": int,
      "relationship_count": int,
      "nodes": [{"id": ..., "name": ..., "age": ..., "country": ..., "category": ...}, ...],
      "relationships": [{"source": ..., "target": ..., "type": "FRIENDS_WITH"}, ...],
      "sample_node_ids": [...],        # ids known to exist, for lookup/traversal sampling
      "sample_values": {"country": [...]},  # values known to exist, for indexed lookups
      "sample_write_payload": {...}     # a template record for the mixed write workload
    }
"""

import json
from pathlib import Path

REQUIRED_KEYS = {
    "node_count",
    "relationship_count",
    "nodes",
    "relationships",
    "sample_node_ids",
    "sample_values",
    "sample_write_payload",
}


def load_dataset(path):
    with open(path) as f:
        dataset = json.load(f)

    missing = REQUIRED_KEYS - dataset.keys()
    if missing:
        raise ValueError(f"Dataset at {path} is missing required keys: {sorted(missing)}")

    if dataset["node_count"] != len(dataset["nodes"]):
        raise ValueError(
            f"Dataset node_count ({dataset['node_count']}) does not match "
            f"len(nodes) ({len(dataset['nodes'])})"
        )
    if dataset["relationship_count"] != len(dataset["relationships"]):
        raise ValueError(
            f"Dataset relationship_count ({dataset['relationship_count']}) does not match "
            f"len(relationships) ({len(dataset['relationships'])})"
        )

    return dataset


def save_dataset(dataset, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(dataset, f)
