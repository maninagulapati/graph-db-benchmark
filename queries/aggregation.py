"""Logical definition for the aggregation workload."""

AGGREGATION = {
    "name": "aggregation",
    "description": "Count users grouped by a property (default: country).",
    "cypher_reference": "MATCH (u:User) RETURN u.country, count(*)",
}
