# Graph Database Performance Benchmarking

A reproducible framework for comparing graph database platforms on the
same dataset, the same logical workloads, and the same client
environment. The goal is credible measurement and root-cause analysis,
not a "fastest database" ranking — see [Goals](#2-goals).

## Table of contents

1. [Overview](#1-overview)
2. [Goals](#2-goals)
3. [Databases Compared](#3-databases-compared)
4. [Database Selection](#4-database-selection)
5. [Environment and Resources](#5-environment-and-resources)
6. [Dataset](#6-dataset)
7. [Dataset Preparation](#7-dataset-preparation)
8. [Dataset Loading](#8-dataset-loading)
9. [Benchmark Methodology](#9-benchmark-methodology)
10. [Workloads](#10-workloads)
11. [Warm-Up Strategy](#11-warm-up-strategy)
12. [Statistical Method](#12-statistical-method)
13. [Results](#13-results)
14. [Charts](#14-charts)
15. [Performance Analysis](#15-performance-analysis)
16. [Root-Cause Analysis](#16-root-cause-analysis)
17. [Concurrency Analysis](#17-concurrency-analysis)
18. [Limitations](#18-limitations)
19. [Reproduction](#19-reproduction)
20. [Configuration](#20-configuration)
21. [Security](#21-security)
22. [Conclusion](#22-conclusion)

---

## 1. Overview

This benchmark evaluates data ingestion, point/indexed lookups, 1/2/3-hop
graph traversal, aggregation, and concurrent read/write workloads across
multiple graph database platforms, measuring latency (p50/p95/p99),
throughput, and error rate under a shared warm-up and iteration
methodology. Every workload is defined logically once (`queries/*.py`)
and translated per-platform by a small adapter (`src/adapters/`), so the
same benchmark harness (`src/benchmark/runner.py`) drives every database
identically.

## 2. Goals

- Load the same dataset into every platform and verify equivalence
  before measuring anything.
- Execute logically identical workloads per platform, even where the
  query language or capabilities differ (see [Database Selection](#4-database-selection)).
- Warm up before measuring, and measure enough iterations for stable
  percentiles; report cold vs. warm separately rather than only steady-state.
- Record every individual query's latency and outcome — never only an
  average — so results can be re-analyzed later without re-running anything.
- Sweep concurrency levels for the mixed read/write workload and track
  throughput, tail latency, and error rate together.
- Document resource allocation, deployment, and region per database, and
  flag rather than hide any unavoidable asymmetry.
- Produce machine-readable raw/processed results, charts, and a written
  analysis that distinguishes observation from hypothesis.
- Verify query *correctness* separately from performance (`tests/test_adapter_correctness.py`).

## 3. Databases Compared

| Database | Role | Query interface | Deployment |
| --- | --- | --- | --- |
| **CognoDB Cloud** | Managed cloud graph DB | Bolt + Cypher | Free-tier managed instance, single fixed region |
| **Kùzu** | Embedded graph DB | Cypher subset | In-process, no server, no network |

Three further slots (`src/adapters/database_c.py`–`database_e.py`) are
scaffolded against the same `GraphDatabaseAdapter` interface but not yet
implemented — see [Database Selection](#4-database-selection) for why
these two were prioritized and what filling in the rest would take.

## 4. Database Selection

**CognoDB Cloud** was the platform this benchmark was originally built
against — a managed, Bolt/Cypher-compatible graph database. It represents
the "real managed cloud service" category.

**Kùzu** was added specifically to satisfy the requirement that this be a
*comparison*, not a single-platform measurement. It was chosen because:

- It's a real, embedded graph database (not a mock or stub) — genuinely
  executing Cypher against genuinely stored graph data.
- It requires no account, signup, or credentials — installable with
  `pip install kuzu`, so it doesn't block progress waiting on
  provisioning.
- Its deployment model (in-process, zero network hop) is a deliberate,
  informative *contrast* to CognoDB's managed-cloud model, not an
  attempt at an apples-to-apples stand-in for it. That asymmetry is
  documented throughout — see [Limitations](#18-limitations) and
  [Root-Cause Analysis](#16-root-cause-analysis) — rather than glossed
  over.

The remaining three slots exist so a third, fourth, or fifth platform
(another managed cloud service, or a self-hosted deployment) can be
added later by implementing `GraphDatabaseAdapter` the same way
`cognodb_adapter.py` and `kuzu_adapter.py` do.

## 5. Environment and Resources

### Database resources

| Database | vCPU | RAM | Storage | Deployment | Region | Tier |
| --- | --- | --- | --- | --- | --- | --- |
| CognoDB | burst to 0.5 | 512 MB | 1 GiB | Managed cloud, free tier | single fixed region (not disclosed) | Free (c0) |
| Kùzu | shares host (12 logical cores) | shares host (~15 GB) | local disk, unbounded | Embedded, in-process | n/a — runs in the client process | n/a — open source |

CognoDB's console reports 512 MB RAM for this tier; some assignment
documentation elsewhere mentions 256 MB — the console's advertised value
is reported here since it reflects what's actually provisioned (engine
v0.9.11; specific instance identifiers withheld from this write-up).

Kùzu's row is *not* a comparable resource allocation — it isn't capped at
all; it simply uses whatever the benchmark client machine has free. This
is a structural fairness asymmetry, not a numbers difference, and is
treated as one throughout this document.

### Benchmark client environment

Captured automatically by `src/benchmark/environment.py` on every run
(`results/raw/environment.json`), so it can't silently drift out of date:

| Field | Value |
| --- | --- |
| OS | Linux, kernel 6.8, x86_64 |
| CPU | 12 logical cores (13th Gen Intel Core i5-1335U) |
| Memory | ~15.3 GB total |
| Python | 3.13.2 |
| `neo4j` driver | 6.2.0 |
| `kuzu` | 0.11.3 |
| `matplotlib` | 3.11.1 |
| `PyYAML` | 6.0.3 |
| `python-dotenv` | 1.2.2 |
| Benchmark version | 0.2.0 |
| Network path | Client → public internet → CognoDB (single fixed region); Kùzu has no network path (in-process) |

## 6. Dataset

**Source:** [SNAP email-Enron](https://snap.stanford.edu/data/email-Enron.html)
— a communication network where an edge indicates two Enron employee
email addresses exchanged mail. Originally released by William Cohen at
CMU.

**Citation** (SNAP's terms are attribution-only — freely available, no
formal license restriction):

> J. Leskovec, K. Lang, A. Dasgupta, M. Mahoney. "Community Structure in
> Large Networks: Natural Cluster Sizes and the Absence of Large
> Well-Defined Clusters." *Internet Mathematics* 6(1), 29–123, 2009.

**Full source graph:** 36,692 nodes / 367,662 directed edges.
**What this benchmark actually loads:** 22,931 nodes / 150,000
relationships — a documented cap, not the full graph (see
[Dataset Preparation](#7-dataset-preparation) for why).

**Schema:**

- Node label `User`: `id` (original SNAP integer id), `name`, `age`,
  `country`, `category` — the latter three synthesized (see below).
- Relationship type `FRIENDS_WITH` (directed, no properties) — a
  relabeling of "exchanged email," a real semantic stretch made to fit
  this benchmark's schema and called out explicitly rather than left
  implicit.

Full detail lives in [`data/README.md`](data/README.md).

## 7. Dataset Preparation

Automated by `scripts/prepare_dataset.py` (backed by
`src/datasets/real_world.py`):

1. Download the raw SNAP edge-list file (skipped if already present
   locally).
2. Take the first 150,000 edge lines in the source file's original
   order. The full graph (367,662 relationships) already exceeds this
   benchmark's 100k–500k target, but risked exceeding CognoDB's
   free-tier limits (512 MB RAM, 1 GiB storage); 150,000 was chosen as a
   safe margin under those limits while still comfortably clearing the
   100,000-relationship minimum.
3. Take every node referenced by those edges (22,931 of the 36,692
   total).
4. Synthesize `name`/`age`/`country`/`category` per node with a fixed
   seed (42) — the source file has no node properties, only topology,
   so the same node id always gets the same synthetic properties across
   regenerations.
5. Restrict the *sampled starting nodes* used for lookup/traversal
   workloads to node ids that have at least one outgoing edge. SNAP ids
   are sparse, and a truncated subset means many ids only ever appear as
   an edge *target* — sampling from all ids uniformly made 1/2/3-hop
   traversal trivially empty for a large fraction of draws during initial
   testing; this was caught and fixed before the reported run (see
   [Root-Cause Analysis](#16-root-cause-analysis)).

## 8. Dataset Loading

Each adapter uses a different, platform-idiomatic loading mechanism —
deliberately not forced to match, per this project's own methodology:

| Database | Mechanism | Nodes/sec | Relationships/sec | Total time |
| --- | --- | ---: | ---: | ---: |
| CognoDB | Driver-based `UNWIND` batching (batch size 1,000) | _PENDING_ | _PENDING_ | _PENDING_ |
| Kùzu | Bulk `COPY FROM` CSV import | _PENDING_ | _PENDING_ | _PENDING_ |

_(Filled in from `results/raw/benchmark_raw.json` after the reported run — see [Results](#13-results).)_

## 9. Benchmark Methodology

```text
load config -> connect -> load dataset -> verify -> warm up
-> execute workloads -> collect measurements -> summarize -> report -> chart
```

- **Iterations:** 20 warm-up iterations (each exercising point lookup +
  all three traversal depths), 100 measured iterations per workload.
- **Randomized starting nodes:** a fresh `random.Random(42)` instance is
  created per database for the sequential single-client workloads, so
  every database walks the *exact same sequence* of "random" starting
  nodes (README "Randomized Starting Nodes") rather than independently
  random ones. The concurrent mixed workload intentionally does not use
  this seeded generator — sharing one `Random` instance across threads
  would introduce its own thread-safety problems, and exact
  reproducibility isn't the goal there.
- **Dataset verification** happens before any performance measurement;
  a count mismatch aborts that database's run rather than silently
  continuing.

## 10. Workloads

### 10.1 Point Lookup
`MATCH (u:User {id: $id}) RETURN u` — exactly one node, by a randomly
sampled valid id.

### 10.2 Indexed Lookup

`MATCH (u:User) WHERE u.country = $value RETURN u`. Index support
differs by platform — documented rather than assumed equal:

| Database | Indexed properties | Notes |
| --- | --- | --- |
| CognoDB | `id` (unique constraint), `country` (range index) | Both created at load time; verified against CognoDB's real Cypher dialect. |
| Kùzu | `id` (automatic primary key) only | Kùzu's Cypher parser has no `CREATE INDEX` statement at all (verified empirically) — `country` lookups are an unindexed full-table-scan filter. |

### 10.3–10.5 Graph Traversal (1/2/3-hop)
`MATCH (u:User {id: $id})-[:FRIENDS_WITH]->(f) RETURN f`, extended to
two and three hops (the 3-hop form uses `*3` — exact length, not
"within" 3 hops). See `queries/traversal.py`.

### 10.6 Aggregation
`MATCH (u:User) RETURN u.country AS group_key, count(*) AS c`.

### 10.7 Mixed Read/Write
Configurable read/write ratio (`config/workloads.yaml`, currently 80/20),
swept across 1/10/40 concurrent clients, each client issuing point
lookups (read) or a synthetic insert (write) back-to-back for a fixed
duration. Tracks total/successful/failed operations, throughput, error
rate, and p50/p95 together — not throughput alone.

## 11. Warm-Up Strategy

```text
Connect -> Load -> Verify -> Warm-up queries (recorded, phase=warmup)
-> Benchmark queries (recorded, phase=benchmark) -> Compare cold vs warm
```

Unlike simply discarding warm-up results, this harness *keeps* them,
tagged `phase=warmup`, specifically so cold-start behavior (first queries
after load) can be compared directly against steady-state (`phase=benchmark`)
for the same workload — see [Results](#13-results) for the actual
cold-vs-warm table.

## 12. Statistical Method

Every individual query execution is recorded (`src/benchmark/latency.py`),
including failures, tagged with the phase it ran in. p50/p95/p99,
min/max/mean/stdev are computed from raw latencies
(`src/benchmark/metrics.py`) so they can be recomputed later from
`results/raw/benchmark_raw.json` without re-running anything.

`src/benchmark/report.py` turns those raw records into a flat per-workload
summary (CSV + JSON), the full results matrix, a cold-vs-warm table, and
an anomaly list — any successful measurement more than 10x its own
workload's own p50 is flagged for investigation, never silently averaged
in or dropped.

## 13. Results

_PENDING — benchmark run in progress against the real 150,000-relationship
dataset. This section will be replaced with the actual results matrix
(loading, lookups, traversals, aggregation, mixed workload, cold vs warm,
concurrency) once it completes._

## 14. Charts

Generated by `src/benchmark/charts.py` into `results/charts/`:

- `traversal_p50.png` / `traversal_p95.png` — 1/2/3-hop latency per database
- `ingestion.png` — nodes/sec and relationships/sec per database
- `throughput_vs_concurrency.png`, `latency_vs_concurrency.png`,
  `error_rate_vs_concurrency.png` — the concurrency sweep

Colors follow a fixed, colorblind-validated per-database assignment that
stays stable across every chart, regardless of which subset of databases
a given chart happens to include.

_PENDING — charts will be regenerated from the real dataset run._

## 15. Performance Analysis

_PENDING — written once real results exist._

## 16. Root-Cause Analysis

Two methodology issues were found and fixed *during* this project, worth
recording here as findings rather than hiding as a clean history:

- **Session-per-query overhead.** The CognoDB adapter originally opened a
  new Bolt session for every single query. An early test run showed
  point lookup, 1-hop traversal, indexed lookup, and aggregation all
  sitting at a suspiciously uniform ~265–285ms, while only 3-hop
  traversal broke away from that floor — strongly suggesting the
  uniform baseline was session-open + network round-trip cost, not
  query execution time. Fixed by reusing one session per thread
  (`self._session()` in `cognodb_adapter.py`) instead of opening one per
  call. See [Performance Analysis](#15-performance-analysis) for whether
  this fix actually changed the numbers once real results land — a
  possible alternative explanation is that the floor is genuinely
  irreducible network RTT to CognoDB's region, in which case the fix
  helps correctness/design but won't move the measured latency much.
  That distinction is decided by evidence, not assumed.
- **Traversal sampling bug.** Sampling *any* node id (not just ones with
  outgoing edges) for the traversal workloads made 1/2/3-hop trivially
  empty for a large fraction of draws, since the dataset's node ids are
  sparse and many only appear as an edge target after truncation. Fixed
  in `src/datasets/real_world.py` by restricting the traversal sample to
  ids known to have at least one outgoing edge.
- **Write-counter collision bug.** Both adapters computed the next
  "fresh" id for mixed-workload writes as `dataset["node_count"]`, which
  is only safe when ids are contiguous from 0 — true for the synthetic
  dataset, false for the real one (SNAP ids are sparse up to 36,691).
  This crashed `write()` with a primary-key violation until caught by a
  pre-run smoke test and fixed to use `max(id)` instead.

Further analysis — comparing CognoDB vs. Kùzu's actual numbers — is
pending the real run; expected discussion topics include the
embedded-vs-network deployment gap and the indexing asymmetry documented
in [Workloads](#10-workloads).

## 17. Concurrency Analysis

_PENDING — written once the real concurrency sweep completes for both
databases._

## 18. Limitations

- **Only 2 of the intended platform lineup are real.** Three adapter
  slots remain unimplemented stubs. This is a two-database comparison,
  not a five-database one.
- **CognoDB vs. Kùzu is not a resource-fair comparison, and isn't meant
  to be treated as one.** CognoDB is capped at 0.5 burst vCPU / 512MB
  RAM; Kùzu runs embedded with the full host machine available and zero
  network hop. Any latency gap between them reflects *both* query-engine
  differences *and* this deployment asymmetry — this document does not
  attempt to separate the two without further evidence.
- **Dataset is a documented subset, not the full source graph.** 150,000
  of 367,662 available relationships, to stay within CognoDB's free-tier
  storage/compute limits. See [Dataset Preparation](#7-dataset-preparation).
- **Node properties are synthetic.** The source graph has no `age`/
  `country`/`category` — these are seeded-random, not real Enron data.
- **Indexing capability differs by platform**, not just index
  configuration choice — Kùzu has no secondary-index mechanism at all in
  its current Cypher dialect (verified empirically, not assumed).
- **Single benchmark run, single client machine, single point in time.**
  Run-to-run variance and multi-region client effects haven't been
  characterized.
- **CognoDB's true resource ceiling is partly undocumented by the
  platform itself** — the console reports 512MB RAM for this tier while
  some assignment material elsewhere says 256MB; this document reports
  the console's value as the more authoritative source, but the
  discrepancy itself is unresolved.
- **The random seed (42) governs only the sequential single-client
  workloads.** The concurrent mixed workload's node/operation selection
  is intentionally unseeded (see [Benchmark Methodology](#9-benchmark-methodology)).

## 19. Reproduction

```bash
git clone <repository>
cd graph-database-benchmark

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# fill in .env — CognoDB needs real credentials; Kuzu needs none

python scripts/prepare_dataset.py   # downloads + transforms the real dataset
python scripts/setup.py             # validate config + credentials, no DB connection
python scripts/benchmark.py         # load -> verify -> warm up -> measure -> report -> charts

# regenerate processed results / charts from a saved raw run without re-benchmarking
python scripts/report.py
python scripts/charts.py

# run the test suite, including query-correctness checks against a known fixture graph
python -m pytest tests/ -v
```

## 20. Configuration

`config/databases.yaml` lists one entry per platform: whether it's
enabled, which adapter class to load, which env vars hold its
credentials (empty for embedded platforms like Kùzu), and its resource
allocation for the fairness documentation in
[Environment and Resources](#5-environment-and-resources).

`config/workloads.yaml` controls the dataset path, the random seed,
warm-up/iteration counts, lookup and traversal sample sizes, the mixed
workload's read/write ratio and concurrency sweep, and timeouts — all
independent of any specific database.

Credentials always come from `.env` (gitignored), never from the YAML
config files.

## 21. Security

Never commit real credentials. `.env` and `credentials*` are gitignored;
`.env.example` holds only placeholders. Database configuration
(`config/databases.yaml`) references environment variable *names*, never
values. (This was exercised for real during this project, not just
written as policy — a real password briefly ended up in `.env.example`
and was caught, scrubbed from git's object store, and the underlying
credential rotated.)

## 22. Conclusion

_PENDING — final wrap-up written once real results and analysis are in place._

---

## Appendix: Repository structure

```text
config/
  databases.yaml       database list, adapter bindings, resource notes
  workloads.yaml        iteration counts, workload params, concurrency levels, random seed
data/
  README.md              dataset schema, source/citation, preparation steps
src/
  adapters/
    base.py               GraphDatabaseAdapter interface every adapter implements
    cognodb_adapter.py     managed cloud reference adapter (Bolt driver, Cypher)
    kuzu_adapter.py         embedded reference adapter (Cypher subset, bulk CSV load)
    database_[c-e].py      remaining stub slots
  benchmark/
    runner.py             orchestrates load -> verify -> warm up -> measure -> report -> chart
    metrics.py             percentile/summary statistics
    latency.py             per-query latency capture (tagged by phase: warmup/benchmark)
    concurrency.py         mixed read/write concurrency runner
    report.py              raw results -> processed CSV/JSON, results matrix, anomaly flags
    charts.py               matplotlib chart generation
    environment.py          captures the benchmark client's CPU/RAM/OS/driver versions
  datasets/
    loader.py              loads/validates the normalized dataset file
    generator.py            synthetic dataset for developing/smoke-testing the harness
    real_world.py           transforms the real SNAP dataset into the benchmark schema
queries/
  lookup.py, traversal.py, aggregation.py, mixed.py
                            logical workload definitions (Cypher-reference, not executable)
scripts/
  prepare_dataset.py      download + transform the real public dataset
  setup.py                validate config/credentials without connecting
  load.py                  load + verify the dataset into every enabled database
  benchmark.py             run the full benchmark end-to-end (load through charts)
  report.py                regenerate processed results from a saved raw JSON file
  charts.py                 regenerate charts from a saved raw JSON file
results/
  raw/ processed/ charts/     benchmark output (gitignored except structure)
tests/
  test_metrics.py           unit tests for the statistics module
  test_report.py             unit tests for processed-results/anomaly logic
  test_adapter_correctness.py   query-correctness checks against a known fixture graph
```
