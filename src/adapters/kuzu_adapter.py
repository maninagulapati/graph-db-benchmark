"""Kuzu adapter — embedded (in-process), the second real database.

Kuzu is an embedded graph database: no server, no network hop, no
credentials — it opens a local on-disk database file directly in this
process. That's a real architectural difference from CognoDB (a managed
cloud service reached over the network), not just a config difference,
and it's the single biggest thing to account for when comparing the two
platforms' numbers: Kuzu skips an entire network round-trip per query
that CognoDB cannot.

Loading mechanism: unlike CognoDB's UNWIND+CREATE batching, Kuzu's
idiomatic bulk-load path is `COPY ... FROM '<csv>'`, so that's what's used
here — a genuinely different mechanism per database, which the spec
explicitly expects to be documented rather than forced to match.

Indexing: Kuzu's Cypher dialect has no CREATE INDEX statement (verified
empirically — the parser rejects it outright). Only the primary key
(User.id) is indexed. indexed_lookup() on Kuzu is therefore an unindexed
full-table-scan filter on `country` — a genuine platform capability
difference to report, not a bug in this adapter.
"""

import csv
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path

import kuzu

from .base import GraphDatabaseAdapter

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "kuzu_db"

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_property(name):
    if not _SAFE_IDENTIFIER.match(name):
        raise ValueError(f"Unsafe property name for Cypher interpolation: {name!r}")
    return name


def _drain(query_result):
    rows = []
    while query_result.has_next():
        rows.append(query_result.get_next())
    return rows


class KuzuAdapter(GraphDatabaseAdapter):
    def __init__(self, name, config):
        super().__init__(name, config)
        self._db = None
        self._local = threading.local()
        self._write_counter = None
        self._write_lock = threading.Lock()
        # Overridable so correctness tests use an isolated path instead of
        # colliding with a real benchmark run's persistent database.
        self.db_path = Path(config["db_path"]) if config.get("db_path") else DB_PATH

    def connect(self):
        # Kuzu persists to disk by default. Start from a clean directory
        # every time, mirroring the "load into an empty database" precondition
        # load_data()/verify_data() assume — a leftover directory from a
        # previous run would otherwise raise a primary-key violation on
        # reload, exactly like the CognoDB re-run did earlier in this project.
        if self.db_path.is_dir():
            shutil.rmtree(self.db_path)
        elif self.db_path.exists():
            self.db_path.unlink()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(str(self.db_path))

    def _connection(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = kuzu.Connection(self._db)
            self._local.conn = conn
        return conn

    def _run(self, query, consume, **parameters):
        """Run a query on this thread's connection and fully consume the result.

        On failure, drops this thread's cached connection so the next
        call gets a fresh one — mirrors the same defensive pattern in
        cognodb_adapter.py, applied consistently even though Kuzu (no
        network) fails differently than a dropped Bolt connection would.
        """
        try:
            result = self._connection().execute(query, parameters=parameters or None)
            return consume(result)
        except Exception:
            self._local.conn = None
            raise

    def load_data(self, dataset):
        start = time.perf_counter()
        conn = self._connection()

        conn.execute(
            "CREATE NODE TABLE User(id INT64, name STRING, age INT64, "
            "country STRING, category STRING, PRIMARY KEY(id))"
        )
        conn.execute("CREATE REL TABLE FRIENDS_WITH(FROM User TO User)")

        nodes = dataset["nodes"]
        relationships = dataset["relationships"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            nodes_csv = Path(tmp_dir) / "nodes.csv"
            with open(nodes_csv, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["id", "name", "age", "country", "category"])
                for n in nodes:
                    writer.writerow([n["id"], n["name"], n["age"], n["country"], n["category"]])
            conn.execute(f"COPY User FROM '{nodes_csv}' (header=true)")

            rels_csv = Path(tmp_dir) / "relationships.csv"
            with open(rels_csv, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["source", "target"])
                for r in relationships:
                    writer.writerow([r["source"], r["target"]])
            conn.execute(f"COPY FRIENDS_WITH FROM '{rels_csv}' (header=true)")

        elapsed = time.perf_counter() - start
        # max(id), not node_count — dataset ids are sparse SNAP identifiers,
        # not contiguous 0..node_count-1, so node_count can collide with an
        # existing real id (this crashed the mixed workload's write() on
        # the real dataset until caught by a pre-run smoke test).
        self._write_counter = max(n["id"] for n in nodes)

        return {
            "nodes_loaded": len(nodes),
            "relationships_loaded": len(relationships),
            "load_time_seconds": elapsed,
            "nodes_per_second": len(nodes) / elapsed if elapsed else 0.0,
            "relationships_per_second": len(relationships) / elapsed if elapsed else 0.0,
            "batch_size": None,
            "loading_mechanism": "COPY FROM CSV (bulk import)",
        }

    def verify_data(self, expected_nodes, expected_relationships):
        actual_nodes = self._run("MATCH (n:User) RETURN count(n) AS c", lambda r: r.get_next()[0])
        actual_relationships = self._run(
            "MATCH (:User)-[r:FRIENDS_WITH]->(:User) RETURN count(r) AS c", lambda r: r.get_next()[0]
        )

        return {
            "ok": actual_nodes == expected_nodes and actual_relationships == expected_relationships,
            "actual_nodes": actual_nodes,
            "actual_relationships": actual_relationships,
        }

    def point_lookup(self, node_id):
        return self._run(
            "MATCH (u:User {id: $id}) RETURN u",
            lambda r: r.get_next() if r.has_next() else None,
            id=node_id,
        )

    def indexed_lookup(self, property_name, value):
        prop = _safe_property(property_name)
        return self._run(f"MATCH (u:User) WHERE u.{prop} = $value RETURN u", _drain, value=value)

    def traversal_1hop(self, node_id):
        return self._run("MATCH (u:User {id: $id})-[:FRIENDS_WITH]->(f) RETURN f", _drain, id=node_id)

    def traversal_2hop(self, node_id):
        return self._run(
            "MATCH (u:User {id: $id})-[:FRIENDS_WITH]->()-[:FRIENDS_WITH]->(f) RETURN DISTINCT f",
            _drain, id=node_id,
        )

    def traversal_3hop(self, node_id):
        return self._run(
            "MATCH (u:User {id: $id})-[:FRIENDS_WITH*3]->(f) RETURN DISTINCT f",
            _drain, id=node_id,
        )

    def aggregation(self, group_by_property):
        prop = _safe_property(group_by_property)
        return self._run(f"MATCH (u:User) RETURN u.{prop} AS group_key, count(*) AS c", _drain)

    def write(self, data):
        with self._write_lock:
            self._write_counter += 1
            new_id = self._write_counter
        payload = {**data, "id": new_id}
        self._run(
            "CREATE (u:User {id: $id, name: $name, age: $age, country: $country, category: $category})",
            list, **payload,
        )

    def resource_footprint(self):
        # Embedded: it runs inside this very Python process, so "resource
        # usage" is just this process's usage — not separable from the
        # benchmark client itself, unlike a real standalone deployment.
        return {
            "observable": False,
            "notes": "Embedded in-process — no separate resource footprint from the benchmark client itself.",
        }

    def close(self):
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
        if self._db is not None:
            self._db.close()
