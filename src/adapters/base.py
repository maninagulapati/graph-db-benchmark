"""Common interface every database-specific adapter must implement.

The benchmark harness (src/benchmark/runner.py) only ever talks to this
interface — it never depends on a specific driver or query language. Each
method describes a *logical* operation; concrete adapters translate that
into whatever syntax their database uses.
"""

from abc import ABC, abstractmethod


class GraphDatabaseAdapter(ABC):
    """Logical operations required to run the benchmark against one database."""

    def __init__(self, name, config):
        self.name = name
        self.config = config

    @abstractmethod
    def connect(self):
        """Establish a connection/session. Must raise on failure, not swallow it."""

    @abstractmethod
    def load_data(self, dataset):
        """Load `dataset` (see src/datasets/loader.py) into the database.

        Returns a dict with at least: nodes_loaded, relationships_loaded,
        load_time_seconds.
        """

    @abstractmethod
    def verify_data(self, expected_nodes, expected_relationships):
        """Return {"ok": bool, "actual_nodes": int, "actual_relationships": int}."""

    @abstractmethod
    def point_lookup(self, node_id):
        """Fetch exactly one node by unique id."""

    @abstractmethod
    def indexed_lookup(self, property_name, value):
        """Fetch nodes matching a property-value filter."""

    @abstractmethod
    def traversal_1hop(self, node_id):
        """Return neighbors one FRIENDS_WITH hop from node_id."""

    @abstractmethod
    def traversal_2hop(self, node_id):
        """Return nodes two FRIENDS_WITH hops from node_id."""

    @abstractmethod
    def traversal_3hop(self, node_id):
        """Return nodes three FRIENDS_WITH hops from node_id."""

    @abstractmethod
    def aggregation(self, group_by_property):
        """Return counts grouped by `group_by_property`."""

    @abstractmethod
    def write(self, data):
        """Perform a single write operation used by the mixed workload."""

    @abstractmethod
    def close(self):
        """Release connections/sessions."""

    def resource_footprint(self):
        """Return observable runtime resource usage, if the platform exposes any.

        Default: not observable. Override only when the driver/API can report
        real numbers (e.g. a managed-service metrics endpoint) — do not guess.
        Static allocation (vCPU/RAM/storage/tier) belongs in
        config/databases.yaml, not here.
        """
        return {"observable": False}
