"""CognoDB Cloud adapter — a fully implemented reference for the other stub slots.

CognoDB exposes a Bolt endpoint (`bolt+s://...:7687`) and speaks Cypher,
so it's driven with the same official `neo4j` Python driver as a real
Neo4j instance. Translates the logical operations in GraphDatabaseAdapter
(see queries/*.py for the Cypher each one must stay equivalent to) into
real Cypher. Requires the `neo4j` package and COGNODB_URI /
COGNODB_USERNAME / COGNODB_PASSWORD in .env.

Indexing: a uniqueness constraint on User.id and a range index on
User.country are created during load_data(), which is also what the
indexed_lookup workload measures against (README section 14). Verified
against CognoDB's actual Cypher dialect — both CREATE CONSTRAINT/INDEX
succeed on the free tier.

LOAD_BATCH_SIZE is set conservatively for the free-tier instance profile
(0.5 burst vCPU / 512 MB RAM per the CognoDB console) — raise it only
after confirming a larger UNWIND batch doesn't time out or exhaust memory
on that instance size.

Session reuse: point_lookup/traversal/indexed_lookup/aggregation/write
each grab a thread-local session (self._session()) instead of opening a
new one per call. The sequential single-client benchmark loop then reuses
one session across all its iterations; each concurrent worker thread in
the mixed workload still gets its own, since Session objects aren't
safe to share across threads.
"""

import os
import re
import threading
import time

from neo4j import GraphDatabase

from .base import GraphDatabaseAdapter

LOAD_BATCH_SIZE = 1000

# Property names come from config/workloads.yaml, not end-user input, but
# they still get interpolated into Cypher (the driver has no way to
# parameterize a property *name*) — this whitelist is the guard against a
# typo'd config value turning into a Cypher injection vector.
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_property(name):
    if not _SAFE_IDENTIFIER.match(name):
        raise ValueError(f"Unsafe property name for Cypher interpolation: {name!r}")
    return name


class CognoDBAdapter(GraphDatabaseAdapter):
    def __init__(self, name, config):
        super().__init__(name, config)
        self._driver = None
        self._write_counter = None
        self._write_lock = threading.Lock()
        self._local = threading.local()

    def connect(self):
        self._driver = GraphDatabase.driver(
            os.getenv("COGNODB_URI"),
            auth=(os.getenv("COGNODB_USERNAME"), os.getenv("COGNODB_PASSWORD")),
        )
        self._driver.verify_connectivity()

    def _session(self):
        session = getattr(self._local, "session", None)
        if session is None:
            session = self._driver.session()
            self._local.session = session
        return session

    def _run(self, query, consume, **params):
        """Run a query on this thread's session and fully consume the result.

        On failure, drops this thread's cached session so the *next* call
        gets a fresh one — a query that kills the underlying connection
        (e.g. resource exhaustion on the free-tier instance) would
        otherwise leave every subsequent call on this thread permanently
        broken, repeating the same failure for the rest of the run.
        """
        try:
            return consume(self._session().run(query, **params))
        except Exception:
            self._local.session = None
            raise

    def load_data(self, dataset):
        start = time.perf_counter()

        with self._driver.session() as session:
            session.run("CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE")
            session.run("CREATE INDEX user_country_index IF NOT EXISTS FOR (u:User) ON (u.country)")

            nodes = dataset["nodes"]
            for i in range(0, len(nodes), LOAD_BATCH_SIZE):
                batch = nodes[i:i + LOAD_BATCH_SIZE]
                session.run(
                    "UNWIND $batch AS row "
                    "CREATE (u:User {id: row.id, name: row.name, age: row.age, "
                    "country: row.country, category: row.category})",
                    batch=batch,
                )

            relationships = dataset["relationships"]
            for i in range(0, len(relationships), LOAD_BATCH_SIZE):
                batch = relationships[i:i + LOAD_BATCH_SIZE]
                session.run(
                    "UNWIND $batch AS row "
                    "MATCH (a:User {id: row.source}), (b:User {id: row.target}) "
                    "CREATE (a)-[:FRIENDS_WITH]->(b)",
                    batch=batch,
                )

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
            "batch_size": LOAD_BATCH_SIZE,
        }

    def verify_data(self, expected_nodes, expected_relationships):
        with self._driver.session() as session:
            actual_nodes = session.run("MATCH (n:User) RETURN count(n) AS c").single()["c"]
            actual_relationships = session.run(
                "MATCH (:User)-[r:FRIENDS_WITH]->(:User) RETURN count(r) AS c"
            ).single()["c"]

        return {
            "ok": actual_nodes == expected_nodes and actual_relationships == expected_relationships,
            "actual_nodes": actual_nodes,
            "actual_relationships": actual_relationships,
        }

    def point_lookup(self, node_id):
        return self._run("MATCH (u:User {id: $id}) RETURN u", lambda r: r.single(), id=node_id)

    def indexed_lookup(self, property_name, value):
        prop = _safe_property(property_name)
        return self._run(f"MATCH (u:User) WHERE u.{prop} = $value RETURN u", list, value=value)

    def traversal_1hop(self, node_id):
        return self._run(
            "MATCH (u:User {id: $id})-[:FRIENDS_WITH]->(f) RETURN f", list, id=node_id
        )

    def traversal_2hop(self, node_id):
        return self._run(
            "MATCH (u:User {id: $id})-[:FRIENDS_WITH]->()-[:FRIENDS_WITH]->(f) RETURN DISTINCT f",
            list, id=node_id,
        )

    def traversal_3hop(self, node_id):
        return self._run(
            "MATCH (u:User {id: $id})-[:FRIENDS_WITH*3]->(f) RETURN DISTINCT f",
            list, id=node_id,
        )

    def aggregation(self, group_by_property):
        prop = _safe_property(group_by_property)
        return self._run(f"MATCH (u:User) RETURN u.{prop} AS group_key, count(*) AS c", list)

    def write(self, data):
        # Mixed-workload writes must not collide with each other or with
        # the loaded dataset's ids, or the unique constraint would turn
        # concurrent writers into artificial failures. The lock makes the
        # increment atomic — plain `+= 1` is a read-modify-write that two
        # threads can race on.
        with self._write_lock:
            self._write_counter += 1
            new_id = self._write_counter
        payload = {**data, "id": new_id}
        self._run(
            "CREATE (u:User {id: $id, name: $name, age: $age, country: $country, category: $category})",
            list, **payload,
        )

    def resource_footprint(self):
        # The Bolt driver has no API for host-level CPU/memory; that data
        # only exists in the CognoDB console. Static allocation for this
        # instance is recorded in config/databases.yaml instead.
        return {"observable": False, "notes": "Use the CognoDB Cloud console for host-level resource usage."}

    def close(self):
        session = getattr(self._local, "session", None)
        if session is not None:
            session.close()
        if self._driver is not None:
            self._driver.close()
