#!/usr/bin/env python3
"""
Merge the old (v1, all pos-3) + new (v2, varied destinations) EE datasets into one.

WHY: lerobot-train does NOT support a list of repo_ids — the factory raises
NotImplementedError for MultiLeRobotDataset (src/lerobot/datasets/factory.py:113).
So we aggregate both into a single unified dataset that keeps BOTH task labels
(aggregate_datasets unifies the tasks index), which is what the warm-start retrain
trains on. The old 100 episodes act as pos-3 replay / anti-forgetting.

Run on the workstation, with both source datasets present locally under ./data:
    .venv/bin/python ee/merge_v1_v2.py

Then train:  bash ee/train_pi0_fullft_v2.sh   (points at vial-sort-merged-ee)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lerobot.datasets.aggregate import aggregate_datasets

REPO_IDS = ["sari-abdan/vial-sort-v1-ee", "sari-abdan/vial-sort-v2-ee"]
ROOTS = [Path("data/vial-sort-v1-ee"), Path("data/vial-sort-v2-ee")]
AGGR_REPO_ID = "sari-abdan/vial-sort-merged-ee"
AGGR_ROOT = Path("data/vial-sort-merged-ee")


def main():
    for r in ROOTS:
        if not r.exists():
            raise SystemExit(f"missing source dataset: {r}  (pull it locally first)")
    if AGGR_ROOT.exists():
        raise SystemExit(f"{AGGR_ROOT} already exists — delete it to re-merge.")
    aggregate_datasets(REPO_IDS, AGGR_REPO_ID, roots=ROOTS, aggr_root=AGGR_ROOT)
    print(f"Merged {REPO_IDS} -> {AGGR_ROOT}")


if __name__ == "__main__":
    main()
