#!/usr/bin/env python3
"""Look at the FULL 50-step action chunk (not just step 0) and whether it varies with
input. Decides: did the model learn (chunk descends, differs per frame/image) or is it
blind (chunk flat + identical across frames/images)?

Portable: no hardware imports. Paths via env vars (defaults = Thor paths):
    LEREBOT_CKPT  checkpoint dir       (default: pretrained_model)
    LEREBOT_DS    joint-space dataset  (default: /home/robot/my_local_data_v1)
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lerobot" / "src"))

import numpy as np
import torch
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.model.kinematics import RobotKinematics
from lerobot.utils.rotation import Rotation
from lerobot.configs.policies import PreTrainedConfig
from lerobot.policies.pi0 import PI0Policy
from lerobot.policies.factory import make_pre_post_processors
from lerobot.policies.utils import prepare_observation_for_inference

CKPT = os.environ.get("LEREBOT_CKPT", "pretrained_model")
DS_ROOT = os.environ.get("LEREBOT_DS", "/home/robot/my_local_data_v1")
URDF_PATH = str(Path(__file__).parent.parent / "SO101" / "so101_new_calib.urdf")
JOINT_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
CAM_NAMES = ["cam_side", "cam_top", "cam_wrist"]
TASK = "Place the red vial in position 3 of the right rack."


def load_policy_and_processors(ckpt, device):
    cfg = PreTrainedConfig.from_pretrained(ckpt)
    cfg.pretrained_path = ckpt
    if os.path.exists(os.path.join(ckpt, "adapter_config.json")):
        from peft import PeftConfig, PeftModel
        pc = PeftConfig.from_pretrained(ckpt)
        base = PI0Policy.from_pretrained(pretrained_name_or_path=pc.base_model_name_or_path, config=cfg)
        policy = PeftModel.from_pretrained(base, ckpt, config=pc)
    else:
        policy = PI0Policy.from_pretrained(pretrained_name_or_path=ckpt, config=cfg)
    policy = policy.to(device).eval()
    pre, post = make_pre_post_processors(
        policy_cfg=cfg, pretrained_path=ckpt,
        preprocessor_overrides={"device_processor": {"device": str(device)}})
    return policy, pre, post


dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
kin = RobotKinematics(urdf_path=URDF_PATH, target_frame_name="gripper_frame_link", joint_names=JOINT_NAMES)
ds = LeRobotDataset(repo_id="local/diag", root=DS_ROOT)
policy, pre, post = load_policy_and_processors(CKPT, dev)


# Works with EITHER dataset: EE (7D) used as-is, joint (6D) converted via FK.
IS_EE = np.asarray(ds[int((np.array(ds.hf_dataset["episode_index"]) == 0).argmax())]
                   ["observation.state"]).shape[0] == 7
print(f"dataset state dim {'7 -> EE (direct)' if IS_EE else '6 -> joint (FK to EE)'}")


def ee_state(j):
    j = np.asarray(j, float)
    if IS_EE:
        return j.astype(np.float32)
    T = kin.forward_kinematics(j)
    p, r = T[:3, 3], Rotation.from_matrix(T[:3, :3]).as_rotvec()
    return np.array([p[0], p[1], p[2], r[0], r[1], r[2], float(j[5])], np.float32)


def batch_for(idx, zero=False):
    item = ds[idx]
    obs = {"observation.state": ee_state(item["observation.state"].numpy())}
    for c in CAM_NAMES:
        if zero:
            img = np.zeros((480, 640, 3), np.uint8)
        else:
            t = item[f"observation.images.{c}"]
            img = (t.clamp(0, 1) * 255).byte().permute(1, 2, 0).contiguous().numpy()
        obs[f"observation.images.{c}"] = img
    return pre(prepare_observation_for_inference(obs, dev, TASK))


ep = np.array(ds.hf_dataset["episode_index"])
fr = int((ep == 0).argmax())

for label, frac in [("frame@0.05 (approach)", 0.05), ("frame@0.45 (over rack)", 0.45)]:
    idx = fr + int(frac * 875)
    if hasattr(policy, "reset"):
        policy.reset()
    chunk = policy.predict_action_chunk(batch_for(idx))
    z = chunk[0, :, 2].float().cpu().numpy()
    g = chunk[0, :, 6].float().cpu().numpy()
    steps = [0, 5, 10, 20, 30, 40, 49]
    print(f"\n{label}  (NORMALIZED chunk)")
    print("  step :", "  ".join(f"{s:>5d}" for s in steps))
    print("  z    :", "  ".join(f"{z[s]:>5.2f}" for s in steps), f"   (range {z.min():.2f}..{z.max():.2f})")
    print("  grip :", "  ".join(f"{g[s]:>5.2f}" for s in steps), f"   (range {g.min():.2f}..{g.max():.2f})")

if hasattr(policy, "reset"):
    policy.reset()
cA = policy.predict_action_chunk(batch_for(fr + 40))[0].float().cpu().numpy()
if hasattr(policy, "reset"):
    policy.reset()
cB = policy.predict_action_chunk(batch_for(fr + 400))[0].float().cpu().numpy()
print(f"\nchunk difference between frame@40 and frame@400: mean|Δ| = {np.abs(cA-cB).mean():.4f}")

if hasattr(policy, "reset"):
    policy.reset()
cR = policy.predict_action_chunk(batch_for(fr + 400, zero=False))[0].float().cpu().numpy()
if hasattr(policy, "reset"):
    policy.reset()
cZ = policy.predict_action_chunk(batch_for(fr + 400, zero=True))[0].float().cpu().numpy()
print(f"chunk difference real-img vs zero-img (same frame): mean|Δ| = {np.abs(cR-cZ).mean():.4f}")
print("\nIf z range within a chunk is ~0 and Δ between frames ~0 -> decoding/cond dead.")
print("If z descends within the chunk and Δ between frames is sizeable -> model learned.")
