#!/usr/bin/env python3
"""
Workspace coverage sweep for the SO-101 vial-sort setup.

Grids EE target positions across the expected workspace, runs IK at each point,
and reports convergence, position error, and dead zones.
No robot connection required — pure kinematics.

Run from /home/robot/dev/lerebot/:
    conda activate lerobot
    python ee/workspace_sweep.py

Outputs:
    ee/workspace_sweep_results.json   — full per-point data
    ee/workspace_sweep_report.md      — human-readable summary + dead zones
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "lerobot" / "src"))
from lerobot.model.kinematics import RobotKinematics

# ── Config ────────────────────────────────────────────────────────────────────
URDF = str(Path(__file__).parent.parent / "SO101" / "so101_new_calib.urdf")
JOINT_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex",
               "wrist_flex", "wrist_roll", "gripper"]

# Grid bounds (metres). Covers the full expected vial-sort workspace with margin.
X_RANGE = np.arange(0.10, 0.46, 0.05)   # forward reach
Y_RANGE = np.arange(-0.25, 0.26, 0.05)  # lateral (left/right racks)
Z_RANGE = np.arange(0.03, 0.33, 0.05)   # height

# IK starting joints (degrees) — neutral pose close to the task workspace.
# Using the observed home pose from the v1 dataset.
HOME_DEG = np.array([-0.1, -106.0, 96.4, -102.0, -145.0, 3.0])

# Thresholds for flagging a point as problematic
POS_ERR_THRESH_MM = 10.0     # IK considered failed if position error > 10 mm
JOINT_JUMP_THRESH_DEG = 25.0  # warn if adjacent grid points jump > 25° in any joint
IK_ITERATIONS = 50            # placo solve() iterations per point (needs loop to converge)

# Target EE orientation: gripper pointing forward and slightly down.
# This is the identity orientation — the URDF's gripper frame at zero joints.
# Adjust if your task requires a specific wrist orientation.
TARGET_ROT = np.eye(3)

OUT_DIR = Path(__file__).parent
# ─────────────────────────────────────────────────────────────────────────────


def build_target_pose(xyz: np.ndarray, R: np.ndarray) -> np.ndarray:
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = xyz
    return T


def ik_converge(kin: RobotKinematics, T_target: np.ndarray,
                start_q: np.ndarray, n_iter: int = IK_ITERATIONS) -> np.ndarray:
    """Run IK for n_iter steps — placo's solve() needs multiple calls to converge."""
    q = start_q.copy().astype(float)
    for _ in range(n_iter):
        q = kin.inverse_kinematics(
            current_joint_pos=q,
            desired_ee_pose=T_target,
            position_weight=1.0,
            orientation_weight=0.0,  # position-only for broad reachability
        )
    return q


def run_sweep(kin: RobotKinematics) -> list[dict]:
    results = []
    total = len(X_RANGE) * len(Y_RANGE) * len(Z_RANGE)
    done = 0

    for x in X_RANGE:
        for y in Y_RANGE:
            prev_q = HOME_DEG.copy()  # restart from home for each column
            for z in Z_RANGE:
                T_target = build_target_pose(np.array([x, y, z]), TARGET_ROT)
                q_ik = ik_converge(kin, T_target, prev_q)

                T_check = kin.forward_kinematics(q_ik.astype(float))
                pos_err_mm = float(np.linalg.norm(T_check[:3, 3] - np.array([x, y, z])) * 1000)
                reachable = pos_err_mm < POS_ERR_THRESH_MM

                joint_jump = float(np.max(np.abs(q_ik - prev_q)))

                results.append({
                    "x": round(float(x), 3),
                    "y": round(float(y), 3),
                    "z": round(float(z), 3),
                    "reachable": reachable,
                    "pos_err_mm": round(pos_err_mm, 2),
                    "joint_jump_deg": round(joint_jump, 2),
                    "large_jump": joint_jump > JOINT_JUMP_THRESH_DEG,
                    "q_deg": [round(float(v), 2) for v in q_ik],
                })

                prev_q = q_ik if reachable else HOME_DEG.copy()
                done += 1
                if done % 50 == 0:
                    print(f"  {done}/{total} points done...", end="\r", flush=True)

    print(f"  {total}/{total} points done.   ")
    return results


def write_report(results: list[dict]) -> str:
    total = len(results)
    reachable = [r for r in results if r["reachable"]]
    unreachable = [r for r in results if not r["reachable"]]
    large_jumps = [r for r in results if r["large_jump"]]

    pct = len(reachable) / total * 100
    lines = [
        "# Workspace Sweep Report — SO-101 Vial-Sort\n",
        f"Grid: x∈[{X_RANGE[0]:.2f}, {X_RANGE[-1]:.2f}]  "
        f"y∈[{Y_RANGE[0]:.2f}, {Y_RANGE[-1]:.2f}]  "
        f"z∈[{Z_RANGE[0]:.2f}, {Z_RANGE[-1]:.2f}]  step=0.05 m",
        f"Total points: {total}  |  IK threshold: {POS_ERR_THRESH_MM} mm\n",
        "## Summary",
        f"- Reachable: **{len(reachable)}/{total} ({pct:.1f}%)**",
        f"- Unreachable (pos err > {POS_ERR_THRESH_MM} mm): {len(unreachable)}",
        f"- Large joint jumps (>{JOINT_JUMP_THRESH_DEG}°): {len(large_jumps)}\n",
    ]

    if unreachable:
        lines += [
            "## Dead zones (IK did not converge)",
            "| x (m) | y (m) | z (m) | pos err (mm) |",
            "|---|---|---|---|",
        ]
        for r in unreachable[:40]:
            lines.append(f"| {r['x']} | {r['y']} | {r['z']} | {r['pos_err_mm']} |")
        if len(unreachable) > 40:
            lines.append(f"| ... | ... | ... | ({len(unreachable)-40} more) |")
        lines.append("")

    if large_jumps:
        lines += [
            "## Large joint jumps (>25° between adjacent grid points)",
            "These indicate near-singularities or IK discontinuities — avoid in data collection.",
            "| x (m) | y (m) | z (m) | max joint jump (deg) |",
            "|---|---|---|---|",
        ]
        for r in large_jumps[:30]:
            lines.append(f"| {r['x']} | {r['y']} | {r['z']} | {r['joint_jump_deg']} |")
        if len(large_jumps) > 30:
            lines.append(f"| ... | ... | ... | ({len(large_jumps)-30} more) |")
        lines.append("")

    # Recommended safe bounds
    if reachable:
        xs = [r["x"] for r in reachable]
        ys = [r["y"] for r in reachable]
        zs = [r["z"] for r in reachable]
        lines += [
            "## Recommended EE_BOUNDS for ee/teleoperate.py and ee/record.py",
            "Based on reachable points only:",
            f'```python',
            f'EE_BOUNDS = {{',
            f'    "min": [{min(xs):.2f}, {min(ys):.2f}, {min(zs):.2f}],',
            f'    "max": [{max(xs):.2f}, {max(ys):.2f}, {max(zs):.2f}],',
            f'}}',
            f'```',
        ]

    return "\n".join(lines)


def main():
    print(f"Loading kinematics from {URDF} ...")
    kin = RobotKinematics(urdf_path=URDF, target_frame_name="gripper_frame_link",
                          joint_names=JOINT_NAMES)

    n = len(X_RANGE) * len(Y_RANGE) * len(Z_RANGE)
    print(f"Sweeping {n} grid points (x={len(X_RANGE)}, y={len(Y_RANGE)}, z={len(Z_RANGE)}) ...")
    results = run_sweep(kin)

    json_path = OUT_DIR / "workspace_sweep_results.json"
    json_path.write_text(json.dumps(results, indent=2))
    print(f"Results saved to {json_path}")

    report = write_report(results)
    md_path = OUT_DIR / "workspace_sweep_report.md"
    md_path.write_text(report)
    print(f"Report saved to {md_path}")
    print()
    print(report)


if __name__ == "__main__":
    main()
