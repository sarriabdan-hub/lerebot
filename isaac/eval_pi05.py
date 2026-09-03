"""
Roll out a trained pi0/pi0.5 checkpoint in the SIM vial-sort scene — runs in
the NORMAL lerobot env (py3.12), talking to sim_server.py (isaac-venv).

Mirrors the real inference path (ee/rollout_pi0_lora.py / ee/vla_server.py):
- EE-action checkpoints (the v3/v4/v5 flow, state/action = ee.x..ee.gripper_pos):
  sim joints --FK--> EE obs --policy--> EE action --bounds+IK--> sim joint
  targets, using the SAME lerobot processors and the same URDF.
- --joint-space for raw joint-space checkpoints.

No arm needed. The scene is staged automatically from ee/initial_fable_v5.txt
(--v4 for the original single-red-vial scenes), so eval sweeps are a bash loop
over --episode. --save-video also writes a sidecar .json for Robometer scoring.

Run (terminal 1: sim server in isaac-venv; terminal 2, repo root):
    uv run python isaac/eval_pi05.py --checkpoint <ckpt_dir> --episode 3 \
        --save-video isaac/out/rollout_ep3.mp4
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import torch

import sim_config as C
from sheet import make_v4_episodes, parse_sheet
from sim_client import SimClient

from lerobot.configs.policies import PreTrainedConfig
from lerobot.model.kinematics import RobotKinematics
from lerobot.policies.factory import get_policy_class, make_pre_post_processors
from lerobot.policies.utils import make_robot_action, prepare_observation_for_inference
from lerobot.processor import RobotProcessorPipeline
from lerobot.processor.converters import (
    observation_to_transition,
    robot_action_observation_to_transition,
    transition_to_observation,
    transition_to_robot_action,
)
from lerobot.robots.so_follower.robot_kinematic_processor import (
    EEBoundsAndSafety,
    ForwardKinematicsJointsToEE,
    InverseKinematicsEEToJoints,
)

EE_NAMES = ["ee.x", "ee.y", "ee.z", "ee.wx", "ee.wy", "ee.wz", "ee.gripper_pos"]
JOINT_KEYS = [f"{j}.pos" for j in C.JOINT_NAMES]
DS_FEATURES_EE = {"action": {"type": "ACTION", "names": EE_NAMES, "shape": [7]}}
DS_FEATURES_JOINT = {"action": {"type": "ACTION", "names": JOINT_KEYS, "shape": [6]}}


def load_policy(ckpt: str, device: torch.device, n_action_steps: int | None):
    cfg = PreTrainedConfig.from_pretrained(ckpt)
    cfg.pretrained_path = ckpt
    if n_action_steps is not None:
        cfg.n_action_steps = n_action_steps
    policy = get_policy_class(cfg.type).from_pretrained(pretrained_name_or_path=ckpt, config=cfg)
    policy = policy.to(device).eval()
    pre, post = make_pre_post_processors(
        policy_cfg=cfg, pretrained_path=ckpt,
        preprocessor_overrides={"device_processor": {"device": str(device)}},
    )
    return policy, pre, post


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--sim-host", default="127.0.0.1")
    p.add_argument("--sim-port", type=int, default=6060)
    p.add_argument("--episode", type=int, default=0)
    p.add_argument("--v4", action="store_true", help="stage a v4 single-red-vial episode")
    p.add_argument("--task", default=None, help="override the episode's prompt")
    p.add_argument("--seconds", type=float, default=45.0)
    p.add_argument("--n-action-steps", type=int, default=None,
                   help="override policy n_action_steps (real deployment uses 15)")
    p.add_argument("--joint-space", action="store_true")
    p.add_argument("--max-ee-step", type=float, default=0.15,
                   help="per-step EE jump cap (m). Real rig uses 0.05 to protect the "
                        "servo; sim has no hardware, so loosen it so a fast commanded "
                        "move doesn't hard-abort the rollout. Workspace bounds still apply.")
    p.add_argument("--save-video", default=None, help="write side-cam mp4 (+ .json metadata)")
    args = p.parse_args()

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    sim = SimClient(args.sim_host, args.sim_port)
    ep_info = sim.reset(episode=args.episode, v4=args.v4)
    task = args.task or ep_info["task"]
    print(f"episode {ep_info['episode']}: {task!r} -> {ep_info['dest']}")

    policy, pre, post = load_policy(args.checkpoint, device, args.n_action_steps)

    # FK / IK pipelines — identical construction to ee/record.py, same URDF
    kin = RobotKinematics(urdf_path=C.URDF_PATH, target_frame_name="gripper_frame_link",
                          joint_names=C.JOINT_NAMES)
    joints_to_ee = RobotProcessorPipeline(
        steps=[ForwardKinematicsJointsToEE(kinematics=kin, motor_names=C.JOINT_NAMES)],
        to_transition=observation_to_transition, to_output=transition_to_observation,
    )
    ee_to_joints = RobotProcessorPipeline(
        steps=[
            EEBoundsAndSafety(end_effector_bounds=C.EE_BOUNDS, max_ee_step_m=args.max_ee_step),
            InverseKinematicsEEToJoints(kinematics=kin, motor_names=C.JOINT_NAMES,
                                        initial_guess_current_joints=True),
        ],
        to_transition=robot_action_observation_to_transition,
        to_output=transition_to_robot_action,
    )
    ds_features = DS_FEATURES_JOINT if args.joint_space else DS_FEATURES_EE

    frames = []
    n = int(args.seconds * C.FPS)
    with torch.inference_mode():
        for i in range(n):
            t0 = time.perf_counter()
            joint_obs, imgs = sim.obs()
            # Pack the state into a single `observation.state` vector — the key the
            # policy preprocessor + normalizer expect (how the dataset stores it).
            # FK/joint dicts give per-component floats; assemble them in feature order.
            if args.joint_space:
                state = np.array([float(joint_obs[k]) for k in JOINT_KEYS], dtype=np.float32)
            else:
                ee = joints_to_ee(dict(joint_obs))        # ee.x .. ee.gripper_pos floats
                state = np.array([float(ee[k]) for k in EE_NAMES], dtype=np.float32)
            obs_raw = {"observation.state": state}
            obs_raw.update({f"observation.images.{k}": np.asarray(v) for k, v in imgs.items()})

            batch = pre(prepare_observation_for_inference(obs_raw, device, task))
            action = post(policy.select_action(batch))
            action_dict = make_robot_action(action, ds_features)

            if args.joint_space:
                sim.act(action_dict)
            else:
                sim.act(ee_to_joints((action_dict, joint_obs)))

            if args.save_video:
                # side-by-side top | side — cam_top shows the pick/place far better
                # than the side view (which the arm often occludes).
                top, side = np.asarray(imgs["cam_top"]), np.asarray(imgs["cam_side"])
                frames.append(np.concatenate([top, side], axis=1))
            if i % C.FPS == 0:
                st = np.round(state, 3).tolist()
                print(f"t={i // C.FPS:3d}s  state={st}")
            busy = time.perf_counter() - t0
            if busy < 1.0 / C.FPS:
                time.sleep(1.0 / C.FPS - busy)

    if args.save_video and frames:
        import imageio
        # higher-quality H.264 (quality 9/10, yuv420p for universal playback)
        imageio.mimsave(args.save_video, frames, fps=C.FPS, quality=9,
                        codec="libx264", pixelformat="yuv420p", macro_block_size=8)
        # sidecar metadata: Robometer scoring + eval bookkeeping
        meta = {"video": str(args.save_video), "task": task, "episode": ep_info["episode"],
                "dest": ep_info["dest"], "v4": args.v4, "checkpoint": args.checkpoint,
                "seconds": args.seconds}
        meta_path = Path(args.save_video).with_suffix(".json")
        meta_path.write_text(json.dumps(meta, indent=2))
        print(f"wrote {args.save_video} and {meta_path}")

    print("rollout finished — judge the placement from the video/GUI (or run Robometer on it).")


if __name__ == "__main__":
    main()
