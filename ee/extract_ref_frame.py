#!/usr/bin/env python3
"""
Pull a REFERENCE camera frame from a recorded episode into ee/align/, so
cam_align_live.py can compare the CURRENT camera against the recording pose.

Sessions 3-6 (the current camera pose) are dataset episodes 40-119. Pick any
episode in that range (default 60 = session 4) to get a "current pose" reference.

Run on the WS, with the dataset pulled locally:
    .venv/bin/python ee/extract_ref_frame.py                 # episode 60 -> ee/align/
    .venv/bin/python ee/extract_ref_frame.py --episode 100   # a different episode
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lerobot.datasets.lerobot_dataset import LeRobotDataset

CAMS = ["cam_top", "cam_wrist", "cam_side"]
ALIGN_DIR = Path(__file__).parent / "align"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-id", default="sari-abdan/vial-sort-v2-static")
    ap.add_argument("--root", default="./data/vial-sort-v2-static")
    ap.add_argument("--episode", type=int, default=60,
                    help="episode index (40-119 = sessions 3-6 = current pose)")
    args = ap.parse_args()

    ds = LeRobotDataset(args.repo_id, root=args.root)
    from_idx = int(ds.meta.episodes[args.episode]["dataset_from_index"])
    print(f"Episode {args.episode}: first frame is dataset index {from_idx}")

    sample = ds[from_idx]
    ALIGN_DIR.mkdir(parents=True, exist_ok=True)
    for cam in CAMS:
        key = f"observation.images.{cam}"
        if key not in sample:
            print(f"  (no {key} in sample, skipping)")
            continue
        img = sample[key]                      # CHW float tensor in [0,1]
        arr = (img.permute(1, 2, 0).numpy() * 255).astype(np.uint8)  # HWC RGB
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        out = ALIGN_DIR / f"reference_{cam}.png"
        cv2.imwrite(str(out), bgr)
        print(f"  wrote {out}")

    print("\nDone. Now run:  .venv/bin/python ee/cam_align_live.py  -> open http://localhost:8765")


if __name__ == "__main__":
    main()
