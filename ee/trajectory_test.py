#!/usr/bin/env python3
"""
Hand-coded EE-delta trajectory test for the SO-101 vial-sort task.

--probe  Torque off. Physically push follower to each position. Press Enter
         to record. Saves both ee/waypoints.json (EE) and
         ee/joint_waypoints.json (motor joints). Joint positions are used
         directly in --run so IK never picks the wrong solution.

--run    Loads joint positions from probe. Interpolates in joint space at
         30fps. Verifies arrival at each waypoint via FK.

Run from /home/robot/dev/lerebot/:
    conda activate lerobot
    sudo chmod 666 /dev/ttyACM*
    python ee/trajectory_test.py --probe   # record positions (5 min)
    python ee/trajectory_test.py --run     # execute and verify
"""

import argparse
import json
import queue
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "lerobot" / "src"))

from lerobot.model.kinematics import RobotKinematics
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
from lerobot.utils.robot_utils import precise_sleep

# ── Constants ─────────────────────────────────────────────────────────────────
URDF_PATH = str(Path(__file__).parent.parent / "SO101" / "so101_new_calib.urdf")
WAYPOINTS_FILE = Path(__file__).parent / "waypoints.json"
JOINT_WAYPOINTS_FILE = Path(__file__).parent / "joint_waypoints.json"
FPS = 30
STEPS_PER_WAYPOINT = 200   # ~6.7 s per segment at 30 fps
SETTLE_STEPS = 60          # 2 s hold after each waypoint
ARRIVE_TOLERANCE_MM = 25.0

JOINT_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex",
               "wrist_flex", "wrist_roll", "gripper"]

ORDER = ["home", "above_vial", "grasp", "lift", "above_rack", "place", "retract"]

# Gripper in RANGE_0_100 (follower gripper is always 0-100, not degrees)
GRIPPER_STATES = {
    "home":        3.0,
    "above_vial":  3.0,
    "grasp":      40.0,
    "lift":       40.0,
    "above_rack": 40.0,
    "place":       3.0,
    "retract":     3.0,
}

DESCRIPTIONS = {
    "home":
        "Fold the arm to its resting position.\n"
        "  Elbow bent back, arm compact near the base, gripper open.",
    "above_vial":
        "Push the gripper directly ABOVE the red vial.\n"
        "  6-8 cm clearance above it. Centred over the vial shaft.\n"
        "  Look from the side: gripper above vial, NOT touching.",
    "grasp":
        "Descend straight down so the gripper SURROUNDS the vial shaft.\n"
        "  Same x,y as above_vial, lower z.\n"
        "  Gripper tips at mid-height of the vial.",
    "lift":
        "Raise straight UP 8-10 cm from grasp.\n"
        "  Same x,y as grasp, just higher z. Vial clears all obstacles.",
    "above_rack":
        "Hover 6-8 cm ABOVE slot 3 in the RIGHT rack.\n"
        "  Slot 3 = third slot from the front.\n"
        "  Centred directly over the slot opening.",
    "place":
        "Descend into slot 3 until vial bottom is near the slot floor.\n"
        "  Same x,y as above_rack, lower z.",
    "retract":
        "Move back to a safe position away from all objects.\n"
        "  Can be same as home.",
}
# ─────────────────────────────────────────────────────────────────────────────


def make_follower() -> SO101Follower:
    return SO101Follower(SO101FollowerConfig(
        port="/dev/ttyACM0", id="so_follower",
        calibration_dir=Path("/home/robot/dev/lerebot/calibration/robots/so_follower"),
        cameras={}, use_degrees=True,
    ))


def probe_mode():
    """
    Torque off. Push arm to each position by hand, press Enter.
    Saves BOTH waypoints.json (EE positions) and joint_waypoints.json
    (motor joint positions). Run uses joint positions directly — no IK.
    """
    print("=== PROBE MODE ===")
    print("Follower motors will go LIMP. Push the arm to each position by hand.")
    print("Live EE coordinates update every 0.3s. Press Enter to record.\n")
    print("Positions:", " → ".join(ORDER), "\n")

    follower = make_follower()
    kin = RobotKinematics(urdf_path=URDF_PATH, target_frame_name="gripper_frame_link",
                          joint_names=JOINT_NAMES)
    follower.connect()
    motor_names = list(follower.bus.motors.keys())
    follower.bus.disable_torque()
    print("Torque DISABLED — arm is limp.\n")

    ee_waypoints: dict = {}
    joint_waypoints: dict = {}

    try:
        for name in ORDER:
            print(f"{'─'*55}")
            print(f"  POSITION: {name.upper()}")
            print(f"{'─'*55}")
            print(f"  {DESCRIPTIONS[name]}")
            print("\n  Push the arm here, then press Enter.\n")

            enter_q: queue.Queue = queue.Queue()
            threading.Thread(target=lambda: (input(), enter_q.put(True)),
                             daemon=True).start()

            last_t = 0.0
            while enter_q.empty():
                obs = follower.get_observation()
                q = np.array([float(obs[f"{m}.pos"]) for m in motor_names], dtype=float)
                if time.perf_counter() - last_t > 0.3:
                    T = kin.forward_kinematics(q)
                    xyz = T[:3, 3]
                    print(f"\r  EE →  x={xyz[0]:+.4f}m  y={xyz[1]:+.4f}m  z={xyz[2]:+.4f}m   ",
                          end="", flush=True)
                    last_t = time.perf_counter()
                time.sleep(0.05)

            enter_q.get()

            # Record both EE and joint positions
            obs = follower.get_observation()
            q = np.array([float(obs[f"{m}.pos"]) for m in motor_names], dtype=float)
            T = kin.forward_kinematics(q)
            xyz = [round(float(v), 4) for v in T[:3, 3]]
            joints = [round(float(v), 3) for v in q]

            ee_waypoints[name] = xyz
            joint_waypoints[name] = joints
            print(f"\n  ✓  RECORDED  {name}")
            print(f"     EE:     {xyz}")
            print(f"     joints: {joints}\n")

    except KeyboardInterrupt:
        print("\nAborted.")
    finally:
        follower.disconnect()

    if ee_waypoints:
        WAYPOINTS_FILE.write_text(json.dumps(ee_waypoints, indent=2))
        JOINT_WAYPOINTS_FILE.write_text(json.dumps(joint_waypoints, indent=2))
        print(f"Saved {len(ee_waypoints)}/{len(ORDER)} positions.")
        print(f"  EE:     {WAYPOINTS_FILE}")
        print(f"  Joints: {JOINT_WAYPOINTS_FILE}")
        missing = [n for n in ORDER if n not in ee_waypoints]
        if missing:
            print(f"Missing: {missing}. Re-run --probe.")
        else:
            print("\nAll done. Run:  python ee/trajectory_test.py --run")


def run_mode():
    """
    Load probed joint positions. Interpolate in joint space. Verify via FK.
    Uses GRIPPER_STATES to set gripper at each waypoint (open/close at the
    right moments), overriding whatever the gripper happened to be at during probe.
    """
    if not JOINT_WAYPOINTS_FILE.exists():
        print(f"ERROR: {JOINT_WAYPOINTS_FILE} not found.")
        print("Run --probe first to record positions.")
        return

    joint_wp_raw = json.loads(JOINT_WAYPOINTS_FILE.read_text())
    ee_waypoints = json.loads(WAYPOINTS_FILE.read_text()) if WAYPOINTS_FILE.exists() else {}

    # Check all waypoints present
    missing = [n for n in ORDER if n not in joint_wp_raw]
    if missing:
        print(f"ERROR: Missing waypoints in joint_waypoints.json: {missing}")
        print("Re-run --probe.")
        return

    print("\n=== RUN MODE ===")
    print("Trajectory:", " → ".join(ORDER))
    print(f"Steps/waypoint: {STEPS_PER_WAYPOINT}  settle: {SETTLE_STEPS}  FPS: {FPS}\n")

    kin = RobotKinematics(urdf_path=URDF_PATH, target_frame_name="gripper_frame_link",
                          joint_names=JOINT_NAMES)
    follower = make_follower()
    follower.connect()
    motor_names = list(follower.bus.motors.keys())

    # Build joint targets: use probed arm joints + task gripper state
    joint_targets: dict[str, np.ndarray] = {}
    for name in ORDER:
        q = np.array(joint_wp_raw[name], dtype=float)
        q[-1] = GRIPPER_STATES[name]   # override gripper with task state
        joint_targets[name] = q

    results = []
    try:
        obs = follower.get_observation()
        q_current = np.array([float(obs[f"{m}.pos"]) for m in motor_names], dtype=float)
        print(f"Arm start joints: {np.round(q_current, 1).tolist()}\n")

        for name in ORDER:
            q_target = joint_targets[name]
            target_xyz = np.array(ee_waypoints.get(name, [0, 0, 0]), dtype=float)

            print(f"→ '{name}'  joints={np.round(q_target, 1).tolist()}")

            # Linear interpolation in joint space
            for step in range(1, STEPS_PER_WAYPOINT + 1):
                t0 = time.perf_counter()
                alpha = step / STEPS_PER_WAYPOINT
                q_step = q_current + (q_target - q_current) * alpha
                action = {f"{m}.pos": float(q_step[i]) for i, m in enumerate(motor_names)}
                follower.send_action(action)
                precise_sleep(max(1.0 / FPS - (time.perf_counter() - t0), 0.0))

            # Settle
            action_final = {f"{m}.pos": float(q_target[i]) for i, m in enumerate(motor_names)}
            for _ in range(SETTLE_STEPS):
                t0 = time.perf_counter()
                follower.send_action(action_final)
                precise_sleep(max(1.0 / FPS - (time.perf_counter() - t0), 0.0))

            q_current = q_target.copy()

            # Verify via FK
            obs = follower.get_observation()
            q_act = np.array([float(obs[f"{m}.pos"]) for m in motor_names], dtype=float)
            T_act = kin.forward_kinematics(q_act)
            actual_xyz = T_act[:3, 3]

            if ee_waypoints.get(name):
                err_mm = float(np.linalg.norm(actual_xyz - target_xyz) * 1000)
                ok = err_mm < ARRIVE_TOLERANCE_MM
                results.append({"waypoint": name, "err_mm": round(err_mm, 1), "pass": ok})
                print(f"  {'PASS' if ok else 'FAIL'}  actual={np.round(actual_xyz, 4).tolist()}  "
                      f"err={err_mm:.1f}mm")
            else:
                print(f"  done   actual={np.round(actual_xyz, 4).tolist()}")

    except KeyboardInterrupt:
        print("\nAborted.")
    finally:
        follower.disconnect()

    if results:
        print("\n=== Results ===")
        for r in results:
            print(f"  {r['waypoint']:<14} {r['err_mm']:5.1f}mm  {'PASS' if r['pass'] else 'FAIL'}")
        all_pass = all(r["pass"] for r in results)
        print("\nEE-delta trajectory: " + ("ALL PASS ✓" if all_pass else "SOME FAILURES"))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--probe", action="store_true",
                       help="Torque off — push arm to each position, press Enter")
    group.add_argument("--run", action="store_true",
                       help="Execute trajectory using probed positions")
    args = parser.parse_args()

    if args.probe:
        probe_mode()
    else:
        run_mode()


if __name__ == "__main__":
    main()
