"""Generate a synthetic dataset matching the loader's schema.

This exists so the harness can be developed and smoke-tested end-to-end
before a real public dataset (README section 7, 100k+ relationships) is
selected and transformed into the same shape. Do not use generated data
for reported benchmark results — only for exercising the pipeline.
"""

import random

from .loader import save_dataset

COUNTRIES = ["US", "GB", "DE", "IN", "BR", "JP", "CA", "AU", "FR", "NG"]
CATEGORIES = ["standard", "premium", "trial"]


def generate_dataset(node_count=20000, avg_friends_per_user=12, seed=None):
    rng = random.Random(seed)

    nodes = [
        {
            "id": i,
            "name": f"user-{i}",
            "age": rng.randint(18, 80),
            "country": rng.choice(COUNTRIES),
            "category": rng.choice(CATEGORIES),
        }
        for i in range(node_count)
    ]

    relationships = []
    for node in nodes:
        friend_count = max(1, rng.randint(avg_friends_per_user // 2, avg_friends_per_user * 2))
        for _ in range(friend_count):
            target = rng.randrange(node_count)
            if target != node["id"]:
                relationships.append({
                    "source": node["id"],
                    "target": target,
                    "type": "FRIENDS_WITH",
                })

    sample_node_ids = rng.sample(range(node_count), k=min(1000, node_count))

    return {
        "node_count": len(nodes),
        "relationship_count": len(relationships),
        "nodes": nodes,
        "relationships": relationships,
        "sample_node_ids": sample_node_ids,
        "sample_values": {"country": COUNTRIES},
        "sample_write_payload": {
            "id": node_count,
            "name": f"user-{node_count}",
            "age": rng.randint(18, 80),
            "country": rng.choice(COUNTRIES),
            "category": rng.choice(CATEGORIES),
        },
    }


if __name__ == "__main__":
    dataset = generate_dataset()
    save_dataset(dataset, "data/dataset.json")
    print(f"Generated {dataset['node_count']} nodes / {dataset['relationship_count']} relationships -> data/dataset.json")
