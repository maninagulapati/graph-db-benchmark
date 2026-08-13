# Dataset

This directory holds the normalized dataset consumed by every adapter
(`data/dataset.json` by default, per `config/workloads.yaml: dataset.path`).
Its contents are gitignored — the file is regenerated or downloaded, not
committed.

## Schema

See [`src/datasets/loader.py`](../src/datasets/loader.py) for the
authoritative required keys. In short:

```json
{
  "node_count": 100000,
  "relationship_count": 250000,
  "nodes": [{"id": 0, "name": "...", "age": 0, "country": "...", "category": "..."}],
  "relationships": [{"source": 0, "target": 1, "type": "FRIENDS_WITH"}],
  "sample_node_ids": [0, 1, 2],
  "sample_values": {"country": ["US", "GB", "..."]},
  "sample_write_payload": {"id": 100000, "name": "...", "age": 0, "country": "...", "category": "..."}
}
```

## The real dataset used for reported results

**Source:** [SNAP email-Enron](https://snap.stanford.edu/data/email-Enron.html)
— a communication network where an edge indicates two Enron employee email
addresses exchanged mail. Originally released by William Cohen at CMU.

**Citation** (SNAP asks for this in place of a formal license — the dataset
itself is freely available, no usage restriction beyond attribution):

> J. Leskovec, K. Lang, A. Dasgupta, M. Mahoney. "Community Structure in
> Large Networks: Natural Cluster Sizes and the Absence of Large
> Well-Defined Clusters." *Internet Mathematics* 6(1), 29–123, 2009.

**Full source graph:** 36,692 nodes / 367,662 directed edges (each
undirected email relationship stored as two directed lines).

**What we actually load — capped, not the full graph:** 22,931 nodes /
150,000 relationships. The full graph already exceeds the spec's
100k–500k relationship target, but 367,662 relationships risked exceeding
CognoDB's free-tier limits (512 MB RAM, 1 GiB storage, 0.5 burst vCPU).
150,000 was chosen as a safe margin under those limits while still
comfortably clearing the 100,000-relationship minimum. This is a
documented cap, not a silent truncation — see `capped_to_relationships`
in `dataset.json`'s `source` field, and `src/datasets/real_world.py` for
the exact truncation logic (first 150,000 edge-list lines in the source
file's original order, then every node referenced by those edges).

**Transformation applied:** the source file only has topology (an edge
list of integer node ids) — no node properties. `name`/`age`/`country`/
`category` are synthesized per node with a fixed seed (42), so the same
node id always gets the same synthetic properties across regenerations.
The `FRIENDS_WITH` relationship type is a relabeling of "exchanged
email" to fit this benchmark's schema — a real semantic stretch, called
out here rather than left implicit.

**Node labels/types:** `User` (id, name, age, country, category).
**Relationship type:** `FRIENDS_WITH` (source → target, no properties).

Regenerate it with:

```bash
python scripts/prepare_dataset.py
```

This downloads the raw edge list into `data/raw/` (skipped if already
present) and writes `data/dataset.json`.

## Synthetic dataset (smoke-testing only)

For developing/smoke-testing the harness without a real download:

```bash
python -m src.datasets.generator
```

Do not use the synthetic dataset's results in any reported benchmark —
it exists only to exercise the pipeline end-to-end before the real
dataset is loaded.
