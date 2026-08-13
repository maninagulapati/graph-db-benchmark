"""Logical definitions for the point-lookup and indexed-lookup workloads.

These are documentation, not executable queries: each adapter implements
the described operation using its own database's query language (README
section 29, "Logical Query Equivalence"). Keeping the description here in
one place is what lets a reviewer confirm every adapter is measuring the
same logical operation.
"""

POINT_LOOKUP = {
    "name": "point_lookup",
    "description": "Retrieve exactly one node by its unique id.",
    "cypher_reference": "MATCH (u:User {id: $id}) RETURN u",
    "expected_result": "exactly one node",
}

INDEXED_LOOKUP = {
    "name": "indexed_lookup",
    "description": "Retrieve all nodes matching a property-value filter.",
    "cypher_reference": "MATCH (u:User {country: $country}) RETURN u",
    "expected_result": "zero or more nodes sharing the given property value",
}
