#!/usr/bin/env python3
"""
Merge the existing 78 paraphrased EE episodes (vial-sort-v4-ee) with the 40 NEW
EE episodes (vial-sort-v4-new-ee) into one trainable dataset (vial-sort-v4-merged-ee).

WHY a merge: lerobot-train does NOT accept a list of repo_ids (factory raises
NotImplementedError for MultiLeRobotDataset). aggregate_datasets unifies the tasks
index so BOTH sets of paraphrases coexist in one dataset.

ORDER MATTERS — paraphrase the NEW set FIRST, then merge:
    1. convert joint -> ee:   ee/convert_dataset.py  (-> data/vial-sort-v4-new-ee, template labels)
    2. paraphrase the NEW set ONLY (it still has clean "...position N of the {rack} rack." labels):
         .venv/bin/python ee/paraphrase_tasks.py --root ./data/vial-sort-v4-new-ee --repo-id sari-abdan/vial-sort-v4-new-ee
       (paraphrase_tasks.py's regex needs the template label; the existing 78 are ALREADY
        paraphrased and would crash it — so we never run it on vial-sort-v4-ee. This is why
        we paraphrase the new set BEFORE merging.)
    3. this script:           .venv/bin/python ee/merge_v4.py
    4. train:                 bash ee/train_pi05_v4.sh   (points at vial-sort-v4-merged-ee)

Run on the workstation with both source datasets present locally under ./data.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lerobot.datasets.aggregate import aggregate_datasets

REPO_IDS = ["sari-abdan/vial-sort-v4-ee", "sari-abdan/vial-sort-v4-new-ee"]
ROOTS = [Path("data/vial-sort-v4-ee"), Path("data/vial-sort-v4-new-ee")]
AGGR_REPO_ID = "sari-abdan/vial-sort-v4-merged-ee"
AGGR_ROOT = Path("data/vial-sort-v4-merged-ee")


def main():
    for r in ROOTS:
        if not r.exists():
            raise SystemExit(f"missing source dataset: {r}  (pull/convert it locally first)")
    if AGGR_ROOT.exists():
        raise SystemExit(f"{AGGR_ROOT} already exists — delete it to re-merge.")
    aggregate_datasets(REPO_IDS, AGGR_REPO_ID, roots=ROOTS, aggr_root=AGGR_ROOT)
    print(f"\nMerged {REPO_IDS}\n  -> {AGGR_ROOT}")

    # sanity print: episode + task count
    import json
    info = json.load(open(AGGR_ROOT / "meta" / "info.json"))
    print(f"  total_episodes={info['total_episodes']}  total_frames={info['total_frames']}  total_tasks={info['total_tasks']}")
    print("  expect ~118 episodes (78 + 40).")


if __name__ == "__main__":
    main()
