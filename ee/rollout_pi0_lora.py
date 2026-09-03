#!/usr/bin/env python3
"""
π0 LoRA real-robot inference for SO-101 vial-sort.

Runs the fine-tuned policy at 30 Hz.  Each trial lasts `--duration`
seconds; afterwards the user logs pass/fail to ee/smoke_test_log.csv.

Usage (Jetson Thor, from lerobot repo root):
    python ee/rollout_pi0_lora.py \
        --checkpoint outputs/train/vial-sort-pi0-lora/checkpoints/last/pretrained_model

Dry-run (workstation, no robot — verifies load + measures latency):
    python ee/rollout_pi0_lora.py \
        --checkpoint outputs/train/vial-sort-pi0-lora/checkpoints/last/pretrained_model \
        --dry-run

Controls during a trial:
    Ctrl+C  abort trial early (logged as ABORT)
"""

import argparse
import csv
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np
import torch

from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig
from lerobot.configs.policies import PreTrainedConfig
from lerobot.model.kinematics import RobotKinematics
from lerobot.policies.factory import get_policy_class, make_pre_post_processors
from lerobot.policies.pi0 import PI0Policy  # noqa: F401  (PEFT base path below)
from lerobot.policies.utils import make_robot_action, prepare_observation_for_inference
from lerobot.processor import RobotProcessorPipeline
from lerobot.processor.converters import (
    observation_to_transition,
    robot_action_observation_to_transition,
    transition_to_observation,
    transition_to_robot_action,
)
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
from lerobot.robots.so_follower.robot_kinematic_processor import (
    EEBoundsAndSafety,
    ForwardKinematicsJointsToEE,
    InverseKinematicsEEToJoints,
)
from lerobot.types import RobotAction, RobotObservation
from lerobot.utils.robot_utils import precise_sleep

# ── Constants ─────────────────────────────────────────────────────────────────

URDF_PATH = str(Path(__file__).parent.parent / "SO101" / "so101_new_calib.urdf")
FPS = 30
TASK = "Place the red vial in position 3 of the right rack."

EE_BOUNDS = {
    "min": [0.18, -0.25, 0.03],
    "max": [0.40,  0.25, 0.32],
}
MAX_EE_STEP_M = 0.05

# Action feature names — must match training dataset.
DS_FEATURES = {
    "action": {
        "type": "ACTION",
        "names": ["ee.x", "ee.y", "ee.z", "ee.wx", "ee.wy", "ee.wz", "ee.gripper_pos"],
        "shape": [7],
    }
}

LOG_PATH = Path(__file__).parent / "smoke_test_log.csv"
LOG_FIELDS = [
    "trial", "result", "failure_mode", "notes",
    "infer_lat_ms_mean", "infer_lat_ms_p95", "control_hz_mean",
]
FAILURE_MODES = ["OK", "MissedGrip", "DroppedVial", "Collision", "WrongRack", "ABORT", "OTHER"]


# ── Policy loading ─────────────────────────────────────────────────────────────

def _is_peft_checkpoint(ckpt_path: str) -> bool:
    import os
    return os.path.exists(os.path.join(ckpt_path, "adapter_config.json"))


def load_policy_and_processors(checkpoint: str, device: torch.device):
    ckpt_path = str(checkpoint)
    policy_cfg = PreTrainedConfig.from_pretrained(ckpt_path)
    policy_cfg.pretrained_path = ckpt_path

    # Pick the right policy class from the checkpoint's config (pi0, pi05, ...) instead of
    # hardcoding PI0Policy — a pi05 checkpoint has different weight keys + processors.
    policy_cls = get_policy_class(policy_cfg.type)
    print(f"  policy class: {policy_cls.__name__}  (type={policy_cfg.type})")

    if _is_peft_checkpoint(ckpt_path):
        from peft import PeftConfig, PeftModel
        peft_config = PeftConfig.from_pretrained(ckpt_path)
        base_policy = policy_cls.from_pretrained(
            pretrained_name_or_path=peft_config.base_model_name_or_path,
            config=policy_cfg,
        )
        policy = PeftModel.from_pretrained(base_policy, ckpt_path, config=peft_config)
    else:
        policy = policy_cls.from_pretrained(pretrained_name_or_path=ckpt_path, config=policy_cfg)

    policy = policy.to(device)
    policy.eval()

    preprocessor, postprocessor = make_pre_post_processors(
        policy_cfg=policy_cfg,
        pretrained_path=ckpt_path,
        preprocessor_overrides={"device_processor": {"device": str(device)}},
    )
    return policy, preprocessor, postprocessor


# ── Robot / pipeline setup ─────────────────────────────────────────────────────

def build_robot_and_pipelines(dry_run: bool, ik_from_prev_solution: bool = False):
    cameras = {
        "cam_top": OpenCVCameraConfig(
            index_or_path="/dev/v4l/by-path/platform-a80aa10000.usb-usb-0:4.2.2:1.0-video-index0",
            fps=FPS, width=640, height=480, color_mode="rgb",
        ),
        "cam_wrist": OpenCVCameraConfig(
            index_or_path="/dev/v4l/by-path/platform-a80aa10000.usb-usb-0:4.2.4:1.0-video-index0",
            fps=FPS, width=640, height=480, color_mode="rgb",
        ),
        "cam_side": RealSenseCameraConfig(
            serial_number_or_name="052622071016",
            fps=FPS, width=640, height=480, color_mode="rgb",
            # First coherent frame after a pipeline (re)start on USB-2 can take several
            # seconds (auto-exposure convergence). connect()'s warmup gives the read
            # thread only warmup_s*1000 ms before it aborts, so keep this generous.
            warmup_s=10,
        ),
    }

    follower_config = SO101FollowerConfig(
        port="/dev/ttyACM0",
        id="so_follower",
        calibration_dir=Path("/home/robot/dev/lerebot/calibration/robots/so_follower"),
        cameras=cameras,
        use_degrees=True,
    )
    follower = SO101Follower(follower_config)

    follower_kin = RobotKinematics(
        urdf_path=URDF_PATH,
        target_frame_name="gripper_frame_link",
        joint_names=list(follower.bus.motors.keys()),
    )

    follower_joints_to_ee = RobotProcessorPipeline[RobotObservation, RobotObservation](
        steps=[
            ForwardKinematicsJointsToEE(
                kinematics=follower_kin,
                motor_names=list(follower.bus.motors.keys()),
            ),
        ],
        to_transition=observation_to_transition,
        to_output=transition_to_observation,
    )

    ee_to_follower = RobotProcessorPipeline[tuple[RobotAction, RobotObservation], RobotAction](
        steps=[
            EEBoundsAndSafety(
                end_effector_bounds=EE_BOUNDS,
                max_ee_step_m=MAX_EE_STEP_M,
            ),
            InverseKinematicsEEToJoints(
                kinematics=follower_kin,
                motor_names=list(follower.bus.motors.keys()),
                # False = seed IK from the PREVIOUS SOLUTION (continuous joint trajectory)
                # instead of from noisy measured joints every step (which makes the solver
                # hop between redundant solutions for the same absolute EE pose = the
                # dominant motor-side jitter, "layer B"). Absolute target -> no drift; and
                # unlike the --ik-seed-last hack, no filtered command feeds back into the seed.
                initial_guess_current_joints=not ik_from_prev_solution,
            ),
        ],
        to_transition=robot_action_observation_to_transition,
        to_output=transition_to_robot_action,
    )

    if not dry_run:
        follower.connect()

    return follower, follower_joints_to_ee, ee_to_follower


# ── Single-step inference ──────────────────────────────────────────────────────

@torch.inference_mode()
def infer_one_step(
    policy, preprocessor, postprocessor,
    obs_raw: dict, device: torch.device,
) -> tuple[dict, float]:
    """
    Returns (action_ee_dict, inference_latency_seconds).
    action_ee_dict keys: ee.x, ee.y, ee.z, ee.wx, ee.wy, ee.wz, ee.gripper_pos
    """
    obs_batch = prepare_observation_for_inference(obs_raw.copy(), device, TASK)
    obs_batch = preprocessor(obs_batch)

    t0 = time.perf_counter()
    action_chunk = policy.select_action(obs_batch)  # (1, 7) normalized
    torch.cuda.synchronize() if device.type == "cuda" else None
    lat = time.perf_counter() - t0

    action_ee = postprocessor(action_chunk)          # (1, 7) physical units
    action_dict = make_robot_action(action_ee, DS_FEATURES)
    return action_dict, lat


# ── Trial loop ─────────────────────────────────────────────────────────────────

def _show_cameras(obs_raw: dict, window_name: str = "cameras") -> None:
    frames = []
    for key in ["observation.images.cam_top", "observation.images.cam_wrist", "observation.images.cam_side"]:
        if key in obs_raw:
            frame = obs_raw[key]
            if isinstance(frame, np.ndarray):
                frames.append(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    if frames:
        combined = np.concatenate(frames, axis=1)
        combined = cv2.resize(combined, (combined.shape[1] // 2, combined.shape[0] // 2))
        cv2.imshow(window_name, combined)
        cv2.waitKey(1)


def run_trial(
    policy, preprocessor, postprocessor,
    follower, follower_joints_to_ee, ee_to_follower,
    device: torch.device, duration: float, dry_run: bool, visualize: bool = False,
) -> dict:
    """Run one trial. Returns latency/freq stats dict."""
    infer_lats, loop_times = [], []
    n_steps = 0
    aborted = False

    # Synthetic obs for dry-run
    def make_fake_obs():
        return {
            "observation.state": np.zeros(7, dtype=np.float32),
            "observation.images.cam_top":   np.zeros((480, 640, 3), dtype=np.uint8),
            "observation.images.cam_wrist": np.zeros((480, 640, 3), dtype=np.uint8),
            "observation.images.cam_side":  np.zeros((480, 640, 3), dtype=np.uint8),
        }

    t_trial_start = time.perf_counter()
    try:
        while time.perf_counter() - t_trial_start < duration:
            t_loop = time.perf_counter()

            if dry_run:
                obs_raw = make_fake_obs()
                obs_ee  = obs_raw
            else:
                obs_raw: RobotObservation = follower.get_observation()
                obs_ee: RobotObservation  = follower_joints_to_ee(obs_raw)

            if visualize:
                _show_cameras(obs_ee if not dry_run else obs_raw)

            action_dict, lat = infer_one_step(
                policy, preprocessor, postprocessor, obs_ee, device
            )

            if not dry_run:
                follower_joints: RobotAction = ee_to_follower((action_dict, obs_raw))
                follower.send_action(follower_joints)

            infer_lats.append(lat)
            loop_times.append(time.perf_counter() - t_loop)
            n_steps += 1

            precise_sleep(max(1.0 / FPS - (time.perf_counter() - t_loop), 0.0))

    except KeyboardInterrupt:
        aborted = True
        print("\n[Ctrl+C] Trial aborted early.")

    if not infer_lats:
        return {"aborted": aborted, "n_steps": 0,
                "infer_lat_ms_mean": 0, "infer_lat_ms_p95": 0, "control_hz_mean": 0}

    return {
        "aborted": aborted,
        "n_steps": n_steps,
        "infer_lat_ms_mean": float(np.mean(infer_lats)) * 1000,
        "infer_lat_ms_p95":  float(np.percentile(infer_lats, 95)) * 1000,
        "control_hz_mean":   float(1.0 / np.mean(loop_times)),
    }


# ── CSV logging ────────────────────────────────────────────────────────────────

def log_trial(trial_num: int, stats: dict) -> None:
    if stats["aborted"]:
        result, failure_mode, notes = "ABORT", "ABORT", ""
    else:
        print(f"\n--- Trial {trial_num} complete ---")
        print(f"  Inference latency : {stats['infer_lat_ms_mean']:.1f} ms mean"
              f"  /  {stats['infer_lat_ms_p95']:.1f} ms p95")
        print(f"  Control frequency : {stats['control_hz_mean']:.1f} Hz")
        print(f"  Steps             : {stats['n_steps']}")

        print("\nResult? ", end="")
        for i, m in enumerate(FAILURE_MODES):
            print(f"  [{i}] {m}", end="")
        print()
        while True:
            try:
                idx = int(input("Enter number: ").strip())
                if 0 <= idx < len(FAILURE_MODES):
                    break
            except ValueError:
                pass
            print("Invalid — enter a number.")

        failure_mode = FAILURE_MODES[idx]
        result = "OK" if failure_mode == "OK" else "FAIL"
        notes = input("Notes (optional, press Enter to skip): ").strip()

    write_header = not LOG_PATH.exists()
    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "trial": trial_num,
            "result": result,
            "failure_mode": failure_mode,
            "notes": notes,
            "infer_lat_ms_mean": f"{stats['infer_lat_ms_mean']:.1f}",
            "infer_lat_ms_p95":  f"{stats['infer_lat_ms_p95']:.1f}",
            "control_hz_mean":   f"{stats['control_hz_mean']:.1f}",
        })
    print(f"  → Logged to {LOG_PATH}")


# ── Main ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--checkpoint",
        default="outputs/train/vial-sort-pi0-lora/checkpoints/last/pretrained_model",
        help="Path to the LoRA checkpoint directory",
    )
    p.add_argument("--device", default=None,
                   help="cuda / cpu / mps (auto-detected if omitted)")
    p.add_argument("--trials", type=int, default=10,
                   help="Number of smoke-test trials")
    p.add_argument("--duration", type=float, default=30.0,
                   help="Seconds per trial")
    p.add_argument("--dry-run", action="store_true",
                   help="Load model and benchmark latency without robot hardware")
    p.add_argument("--visualize", action="store_true",
                   help="Show live camera feeds in an OpenCV window during trials")
    return p.parse_args()


def main():
    args = parse_args()

    device_str = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    device = torch.device(device_str)
    print(f"Device: {device}")

    print("Loading policy...")
    policy, preprocessor, postprocessor = load_policy_and_processors(args.checkpoint, device)
    print("Policy loaded.")

    if args.dry_run:
        print("\n[dry-run] Warming up with 3 fake forward passes...")
        follower = follower_joints_to_ee = ee_to_follower = None
        # Warm-up (fills action queue, JIT-compiles CUDA kernels)
        fake_obs = {
            "observation.state": np.zeros(7, dtype=np.float32),
            "observation.images.cam_top":   np.zeros((480, 640, 3), dtype=np.uint8),
            "observation.images.cam_wrist": np.zeros((480, 640, 3), dtype=np.uint8),
            "observation.images.cam_side":  np.zeros((480, 640, 3), dtype=np.uint8),
        }
        for _ in range(3):
            infer_one_step(policy, preprocessor, postprocessor, fake_obs, device)
        stats = run_trial(
            policy, preprocessor, postprocessor,
            None, None, None,
            device, duration=10.0, dry_run=True, visualize=args.visualize,
        )
        print(f"\n[dry-run] Results over 10 s:")
        print(f"  Inference latency : {stats['infer_lat_ms_mean']:.1f} ms mean"
              f"  /  {stats['infer_lat_ms_p95']:.1f} ms p95")
        print(f"  Control frequency : {stats['control_hz_mean']:.1f} Hz  "
              f"(target {FPS} Hz)")
        print(f"  Steps completed   : {stats['n_steps']}")
        return

    print("Connecting to robot...")
    follower, follower_joints_to_ee, ee_to_follower = build_robot_and_pipelines(dry_run=False)
    print("Robot connected. Starting trials.\n")

    try:
        for trial in range(1, args.trials + 1):
            input(f"\n[Trial {trial}/{args.trials}] Position the scenario, then press Enter to start...")
            print(f"Running for {args.duration:.0f} s — Ctrl+C to abort early.")
            stats = run_trial(
                policy, preprocessor, postprocessor,
                follower, follower_joints_to_ee, ee_to_follower,
                device, duration=args.duration, dry_run=False, visualize=args.visualize,
            )
            if args.visualize:
                cv2.destroyAllWindows()
            log_trial(trial, stats)
    finally:
        if follower and follower.is_connected:
            follower.disconnect()

    print(f"\nAll {args.trials} trials done. Results: {LOG_PATH}")


if __name__ == "__main__":
    main()
