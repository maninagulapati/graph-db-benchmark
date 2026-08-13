"""Adapter stub for Database D.

Rename this module/class once a real platform is selected (see
config/databases.yaml) and implement each method against that database's
driver, translating the logical operations defined in GraphDatabaseAdapter
into that platform's query language.
"""

from .base import GraphDatabaseAdapter


class DatabaseDAdapter(GraphDatabaseAdapter):
    def connect(self):
        raise NotImplementedError("Select and configure a real database before connecting.")

    def load_data(self, dataset):
        raise NotImplementedError

    def verify_data(self, expected_nodes, expected_relationships):
        raise NotImplementedError

    def point_lookup(self, node_id):
        raise NotImplementedError

    def indexed_lookup(self, property_name, value):
        raise NotImplementedError

    def traversal_1hop(self, node_id):
        raise NotImplementedError

    def traversal_2hop(self, node_id):
        raise NotImplementedError

    def traversal_3hop(self, node_id):
        raise NotImplementedError

    def aggregation(self, group_by_property):
        raise NotImplementedError

    def write(self, data):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError
