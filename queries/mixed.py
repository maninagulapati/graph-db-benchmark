"""Logical definition for the mixed concurrent read/write workload."""

MIXED_WORKLOAD = {
    "name": "mixed_workload",
    "description": (
        "A configurable read/write ratio (see config/workloads.yaml: "
        "mixed_workload.read_percentage) executed by N concurrent clients "
        "for a fixed duration. Reads use point_lookup; writes use write()."
    ),
    "read_operation": "point_lookup",
    "write_operation": "write",
}
