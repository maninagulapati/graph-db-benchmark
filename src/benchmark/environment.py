"""Capture the benchmark client environment (README "Same Client Environment").

Captured automatically rather than hand-typed into the README, so it can
never silently drift out of date relative to the machine that actually
produced a given results/raw/benchmark_raw.json.
"""

import os
import platform
from importlib import metadata

BENCHMARK_VERSION = "0.2.0"

TRACKED_PACKAGES = ["neo4j", "kuzu", "matplotlib", "PyYAML", "python-dotenv"]


def _package_versions():
    versions = {}
    for name in TRACKED_PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _total_memory_gb():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / (1024 * 1024), 1)
    except FileNotFoundError:
        pass
    return None


def capture_environment():
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "os": platform.platform(),
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "total_memory_gb": _total_memory_gb(),
        "package_versions": _package_versions(),
        "network_region_note": (
            "Not auto-detected. This client runs wherever the benchmark is "
            "invoked from; CognoDB is reached over the public internet to "
            "its us-east4 endpoint (see config/databases.yaml), while any "
            "embedded adapter (e.g. Kuzu) runs in-process on this same "
            "machine with zero network hop — that asymmetry is a "
            "methodology caveat, not something these numbers control for."
        ),
    }
