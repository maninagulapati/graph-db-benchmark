"""Transform the SNAP Enron email network into the benchmark's dataset schema.

Source: https://snap.stanford.edu/data/email-Enron.html (J. Leskovec, K. Lang,
A. Dasgupta, M. Mahoney, "Community Structure in Large Networks", Internet
Mathematics 6(1), 2009; originally released by William Cohen at CMU). SNAP
asks only for citation, not a formal license — see data/README.md for the
full citation.

The raw file lists 367,662 directed edges over 36,692 nodes (each undirected
email relationship stored as two directed lines). MAX_RELATIONSHIPS below
caps how many of those lines get used — the full graph is comfortably within
the spec's 100k-500k target already, but the cap keeps load time and storage
well inside a 512MB/1GiB free-tier instance, and is documented rather than
applied silently: see the "capped" field in the returned dataset's metadata.

Node properties (name/age/country/category) don't exist in the source data
— they're synthesized deterministically (seeded) so the same node always
gets the same synthetic properties across runs, since the source graph only
has topology.
"""

import random

COUNTRIES = ["US", "GB", "DE", "IN", "BR", "JP", "CA", "AU", "FR", "NG"]
CATEGORIES = ["standard", "premium", "trial"]

MAX_RELATIONSHIPS = 150_000


def parse_edges(raw_path, max_relationships=MAX_RELATIONSHIPS):
    """Read the raw SNAP edge-list file, returning (edges, capped: bool)."""
    edges = []
    with open(raw_path) as f:
        for line in f:
            if line.startswith("#"):
                continue
            source_str, target_str = line.split()
            edges.append((int(source_str), int(target_str)))
            if len(edges) >= max_relationships:
                break

    with open(raw_path) as f:
        total_lines = sum(1 for line in f if not line.startswith("#"))

    return edges, len(edges) < total_lines


def build_dataset(raw_path, max_relationships=MAX_RELATIONSHIPS, seed=42):
    edges, capped = parse_edges(raw_path, max_relationships)

    node_ids = sorted({n for edge in edges for n in edge})
    rng = random.Random(seed)

    nodes = [
        {
            "id": node_id,
            "name": f"user-{node_id}",
            "age": rng.randint(18, 80),
            "country": rng.choice(COUNTRIES),
            "category": rng.choice(CATEGORIES),
        }
        for node_id in node_ids
    ]

    relationships = [
        {"source": source, "target": target, "type": "FRIENDS_WITH"}
        for source, target in edges
    ]

    # Restricted to nodes with at least one outgoing edge — since ids are
    # sparse SNAP identifiers (not contiguous 0..N-1), many nodes in a
    # truncated subset only ever appear as an edge *target*. Sampling from
    # all node ids uniformly would make 1/2/3-hop traversal trivially
    # empty for a large fraction of draws; every id here is guaranteed to
    # have real outgoing edges to walk.
    source_ids = sorted({source for source, _ in edges})
    sample_node_ids = rng.sample(source_ids, k=min(1000, len(source_ids)))
    next_id = max(node_ids) + 1

    return {
        "node_count": len(nodes),
        "relationship_count": len(relationships),
        "nodes": nodes,
        "relationships": relationships,
        "sample_node_ids": sample_node_ids,
        "sample_values": {"country": COUNTRIES},
        "sample_write_payload": {
            "id": next_id,
            "name": f"user-{next_id}",
            "age": rng.randint(18, 80),
            "country": rng.choice(COUNTRIES),
            "category": rng.choice(CATEGORIES),
        },
        "source": {
            "name": "SNAP email-Enron",
            "url": "https://snap.stanford.edu/data/email-Enron.html",
            "full_graph_nodes": 36692,
            "full_graph_relationships": 367662,
            "capped_to_relationships": max_relationships if capped else None,
        },
    }
