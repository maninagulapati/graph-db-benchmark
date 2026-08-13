"""Logical definitions for the 1/2/3-hop traversal workloads.

See queries/lookup.py for why these are descriptions rather than
executable code — each adapter implements the same logical traversal in
its own query language.
"""

TRAVERSAL_1HOP = {
    "name": "traversal_1hop",
    "description": "Find all users one FRIENDS_WITH relationship from a given user.",
    "cypher_reference": "MATCH (u:User {id: $id})-[:FRIENDS_WITH]->(f) RETURN f",
}

TRAVERSAL_2HOP = {
    "name": "traversal_2hop",
    "description": "Find all users two FRIENDS_WITH relationships from a given user.",
    "cypher_reference": (
        "MATCH (u:User {id: $id})-[:FRIENDS_WITH]->()-[:FRIENDS_WITH]->(f) RETURN f"
    ),
}

TRAVERSAL_3HOP = {
    "name": "traversal_3hop",
    "description": "Find all users three FRIENDS_WITH relationships from a given user.",
    "cypher_reference": "MATCH (u:User {id: $id})-[:FRIENDS_WITH*3]->(f) RETURN f",
}
