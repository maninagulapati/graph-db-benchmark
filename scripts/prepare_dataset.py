#!/usr/bin/env python3
"""Download and transform the real public dataset for this benchmark.

    python scripts/prepare_dataset.py

Downloads the SNAP email-Enron edge list (see src/datasets/real_world.py
for citation/license and the exact transformation applied) into
data/raw/, then writes the normalized data/dataset.json every adapter
consumes. Safe to re-run: skips the download if the raw file already
exists.
"""

import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.datasets.loader import save_dataset  # noqa: E402
from src.datasets.real_world import build_dataset  # noqa: E402

RAW_URL = "https://snap.stanford.edu/data/email-Enron.txt.gz"
RAW_GZ_PATH = REPO_ROOT / "data" / "raw" / "email-Enron.txt.gz"
RAW_TXT_PATH = REPO_ROOT / "data" / "raw" / "email-Enron.txt"


def ensure_raw_file():
    if RAW_TXT_PATH.exists():
        return
    RAW_TXT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not RAW_GZ_PATH.exists():
        print(f"Downloading {RAW_URL} ...")
        urllib.request.urlretrieve(RAW_URL, RAW_GZ_PATH)

    import gzip
    with gzip.open(RAW_GZ_PATH, "rt") as f_in, open(RAW_TXT_PATH, "w") as f_out:
        f_out.write(f_in.read())


def main():
    ensure_raw_file()
    dataset = build_dataset(RAW_TXT_PATH)

    source = dataset["source"]
    print(
        f"Built dataset: {dataset['node_count']} nodes / "
        f"{dataset['relationship_count']} relationships "
        f"(full source graph: {source['full_graph_nodes']} nodes / "
        f"{source['full_graph_relationships']} relationships; "
        f"capped to {source['capped_to_relationships']})"
    )

    output_path = REPO_ROOT / "data" / "dataset.json"
    save_dataset(dataset, output_path)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
