#!/usr/bin/env python3
"""
Convert vial-sort-v1-static (joint-space) → vial-sort-v1-ee (EE-space).

Action and observation.state go from 6D joint positions
    [shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper]
to 7D end-effector pose
    [ee.x, ee.y, ee.z, ee.wx, ee.wy, ee.wz, ee.gripper_pos]
via forward kinematics. Videos and all other metadata are copied unchanged.

Run on the workstation (NOT on Thor):
    cd ~/lerobot
    python ee/convert_dataset.py \
        --src ./data/vial-sort-v1-static \
        --dst ./data/vial-sort-v1-ee \
        --urdf ./SO101/so101_new_calib.urdf

Then push to HuggingFace:
    huggingface-cli upload sari-abdan/vial-sort-v1-ee \\
        ./data/vial-sort-v1-ee --repo-type dataset

Prerequisites on workstation:
    scp -r robot@192.168.123.198:/home/robot/dev/lerebot/SO101/ ./SO101/
    huggingface-cli download sari-abdan/vial-sort-v1-static \\
        --repo-type dataset --local-dir ./data/vial-sort-v1-static
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Support both Thor layout (lerobot/src/lerobot) and workstation pip install
_src = Path(__file__).parent.parent / "lerobot" / "src"
if _src.exists():
    sys.path.insert(0, str(_src))

from lerobot.model.kinematics import RobotKinematics
from lerobot.utils.rotation import Rotation

JOINT_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex",
               "wrist_flex", "wrist_roll", "gripper"]
EE_COLS = ["ee.x", "ee.y", "ee.z", "ee.wx", "ee.wy", "ee.wz", "ee.gripper_pos"]


def joints_to_ee_batch(kin: RobotKinematics, joints: np.ndarray) -> np.ndarray:
    """(N, 6) joint positions → (N, 7) EE poses via FK."""
    out = np.empty((len(joints), 7), dtype=np.float32)
    for i, row in enumerate(joints):
        T = kin.forward_kinematics(row.astype(float))
        pos = T[:3, 3]
        rot = Rotation.from_matrix(T[:3, :3]).as_rotvec()
        # gripper passes through as-is (RANGE_0_100 scale)
        out[i] = [pos[0], pos[1], pos[2], rot[0], rot[1], rot[2], float(row[5])]
    return out


def compute_stats(arr: np.ndarray) -> dict:
    return {
        "min":  arr.min(axis=0).tolist(),
        "max":  arr.max(axis=0).tolist(),
        "mean": arr.mean(axis=0).tolist(),
        "std":  arr.std(axis=0).tolist(),
        "q01":  np.quantile(arr, 0.01, axis=0).tolist(),
        "q99":  np.quantile(arr, 0.99, axis=0).tolist(),
    }


def convert(src: Path, dst: Path, urdf: Path) -> None:
    print(f"Loading kinematics from {urdf} ...")
    kin = RobotKinematics(urdf_path=str(urdf), target_frame_name="gripper_frame_link",
                          joint_names=JOINT_NAMES)

    # ── Set up destination ────────────────────────────────────────────────────
    if dst.exists():
        print(f"Removing existing {dst}")
        shutil.rmtree(dst)
    dst.mkdir(parents=True)

    # Copy everything except data/ and meta/ (we handle those manually)
    for item in src.iterdir():
        if item.name in ("data", "meta"):
            continue
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)

    # ── Update meta/ ──────────────────────────────────────────────────────────
    shutil.copytree(src / "meta", dst / "meta")

    info_path = dst / "meta" / "info.json"
    with open(info_path) as f:
        info = json.load(f)

    ee_feature = {"dtype": "float32", "names": EE_COLS, "shape": [7]}
    info["features"]["action"] = ee_feature
    info["features"]["observation.state"] = ee_feature

    with open(info_path, "w") as f:
        json.dump(info, f, indent=4)
    print("  updated meta/info.json  (action + observation.state → 7D EE)")

    # ── Convert parquet chunks ────────────────────────────────────────────────
    data_src = src / "data"
    data_dst = dst / "data"

    parquet_files = sorted(data_src.rglob("*.parquet"))
    print(f"\nConverting {len(parquet_files)} parquet file(s) ...")

    all_actions: list[np.ndarray] = []
    all_states:  list[np.ndarray] = []

    for pf in parquet_files:
        rel = pf.relative_to(data_src)
        out_path = data_dst / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)

        df = pd.read_parquet(pf)

        if "action" in df.columns:
            joints = np.stack(df["action"].to_numpy()).astype(np.float32)
            ee = joints_to_ee_batch(kin, joints)
            df["action"] = list(ee)
            all_actions.append(ee)

        if "observation.state" in df.columns:
            joints = np.stack(df["observation.state"].to_numpy()).astype(np.float32)
            ee = joints_to_ee_batch(kin, joints)
            df["observation.state"] = list(ee)
            all_states.append(ee)

        df.to_parquet(out_path, index=False)
        print(f"  {rel}")

    # ── Recompute stats.json ──────────────────────────────────────────────────
    stats_path = dst / "meta" / "stats.json"
    if stats_path.exists() and (all_actions or all_states):
        with open(stats_path) as f:
            stats = json.load(f)
        if all_actions:
            stats["action"] = compute_stats(np.concatenate(all_actions, axis=0))
        if all_states:
            stats["observation.state"] = compute_stats(np.concatenate(all_states, axis=0))
        with open(stats_path, "w") as f:
            json.dump(stats, f, indent=4)
        print("\n  updated meta/stats.json")

    print(f"\nDone — EE dataset at: {dst}")
    print(f"  episodes:  {info['total_episodes']}")
    print(f"  frames:    {info['total_frames']}")
    print(f"  action:    {ee_feature}")
    print()
    print("Push to HuggingFace:")
    print(f"  huggingface-cli upload sari-abdan/vial-sort-v1-ee {dst} --repo-type dataset")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src",  type=Path, default=Path("./data/vial-sort-v1-static"))
    ap.add_argument("--dst",  type=Path, default=Path("./data/vial-sort-v1-ee"))
    ap.add_argument("--urdf", type=Path, default=Path("./SO101/so101_new_calib.urdf"))
    args = ap.parse_args()

    if not args.src.exists():
        print(f"ERROR: source dataset not found at {args.src}")
        print("Download it first:")
        print("  huggingface-cli download sari-abdan/vial-sort-v1-static "
              "--repo-type dataset --local-dir ./data/vial-sort-v1-static")
        raise SystemExit(1)

    if not args.urdf.exists():
        print(f"ERROR: URDF not found at {args.urdf}")
        print("Copy from Thor:")
        print("  scp -r robot@192.168.123.198:/home/robot/dev/lerebot/SO101/ ./SO101/")
        raise SystemExit(1)

    convert(args.src, args.dst, args.urdf)


if __name__ == "__main__":
    main()
