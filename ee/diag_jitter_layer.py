#!/usr/bin/env python3
"""Localize the jitter to a LAYER: EE target (policy/RTC) vs joint command (post-IK).

Reads a --trace-motors CSV with three column groups:
  act.ee.*  = policy EE action target (pre-IK)
  cmd.*     = commanded joints (post-IK, sent to motors)
  obs.*     = measured joints (FK input + IK seed)

Key question: when the EE target is nearly STILL, do the commanded joints still
jump? If yes, the InverseKinematicsEEToJoints stage (seeded from noisy measured
joints) is injecting the jitter — downstream of and invisible to RTC/EE smoothing.
"""
import argparse
import numpy as np
import pandas as pd

JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]


def step_std(x):
    return float(np.std(np.diff(x))) if len(x) > 1 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    args = ap.parse_args()
    df = pd.read_csv(args.csv)

    # --- EE target motion (mm) and its step-to-step jitter ---
    ee_xyz = np.stack([df[f"act.ee.{a}"].to_numpy() for a in ("x", "y", "z")], axis=1) * 1000.0  # m->mm
    dee = np.linalg.norm(np.diff(ee_xyz, axis=0), axis=1)  # per-step EE move (mm)
    print(f"rows: {len(df)}")
    print("\n=== EE TARGET (policy/RTC output, pre-IK) ===")
    print(f"  per-step EE move |Δ|: mean {dee.mean():.2f} mm  median {np.median(dee):.2f}  p95 {np.percentile(dee,95):.2f}")
    for a in ("x", "y", "z"):
        print(f"  act.ee.{a} step-std: {step_std(df[f'act.ee.{a}'].to_numpy()*1000):.2f} mm")

    # --- Commanded joint jitter (post-IK) ---
    print("\n=== COMMANDED JOINTS (post-IK, to motors) ===")
    for j in JOINTS:
        c = df[f"cmd.{j}.pos"].to_numpy()
        print(f"  cmd.{j:<14} step-std: {step_std(c):.2f} deg")

    # --- THE ISOLATION TEST: cmd-joint jump when EE target is ~still vs moving ---
    dcmd = np.stack([np.abs(np.diff(df[f"cmd.{j}.pos"].to_numpy())) for j in JOINTS], axis=1)
    dcmd_norm = np.linalg.norm(dcmd, axis=1)  # total joint move per step (deg)
    # classify steps by EE motion
    thr = np.percentile(dee, 33)
    still = dee <= thr           # EE barely moving
    moving = dee > np.percentile(dee, 66)
    print("\n=== ISOLATION: joint command jump vs EE-target motion ===")
    print(f"  EE-STILL steps  (|Δee| <= {thr:.2f} mm):  cmd joint |Δ| mean {dcmd_norm[still].mean():.2f} deg  p95 {np.percentile(dcmd_norm[still],95):.2f}")
    print(f"  EE-MOVING steps (|Δee| >  {np.percentile(dee,66):.2f} mm):  cmd joint |Δ| mean {dcmd_norm[moving].mean():.2f} deg  p95 {np.percentile(dcmd_norm[moving],95):.2f}")
    ratio = dcmd_norm[still].mean() / max(dcmd_norm[moving].mean(), 1e-6)
    print(f"\n  VERDICT: joints move {100*ratio:.0f}% as much when the EE target is STILL as when it's MOVING.")
    if ratio > 0.4:
        print("  => IK INJECTS JITTER: commanded joints jump even with a still EE target.")
        print("     EE-space smoothing (RTC/1-Euro on the action) CANNOT fix this. Fix the IK/joint layer.")
    else:
        print("  => joints track the EE target; jitter originates UPSTREAM (policy/RTC EE output).")

    # --- correlation of EE motion vs joint motion ---
    if len(dee) > 2:
        r = np.corrcoef(dee, dcmd_norm)[0, 1]
        print(f"\n  corr(|Δee|, |Δcmd|) = {r:.2f}  (near 1 = joints follow EE; near 0 = joints move independently)")


if __name__ == "__main__":
    main()
