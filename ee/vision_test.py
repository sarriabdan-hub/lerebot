#!/usr/bin/env python3
"""
THE vision gate: does the model reach toward where the vial actually is?

Feeds the policy the SAME fixed home state (above_vial) but two different camera
images — a NEAR-vial scene and a FAR-vial scene — and compares the predicted grasp
location. State is identical, so any difference is due to VISION alone.

PASS: predicted grasp-x is larger for the FAR scene than the NEAR scene, tracking the
      true vial positions. FAIL: predictions ~identical -> still blind.

Portable: no hardware imports. Set paths via env vars (defaults are the Thor paths):
    LEREBOT_CKPT  checkpoint dir         (default: pretrained_model)
    LEREBOT_DS    joint-space dataset    (default: /home/robot/my_local_data_v1)

Workstation example:
    LEREBOT_CKPT=outputs/train/vial-sort-pi0-divtest/checkpoints/last/pretrained_model \
    LEREBOT_DS=data/vial-sort-v1-static \
    python ee/vision_test.py 49 95
"""
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lerobot" / "src"))

import numpy as np
import torch
from safetensors import safe_open
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
JOINT_WAYPOINTS_PATH = Path(__file__).parent / "joint_waypoints.json"
JOINT_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
CAM_NAMES = ["cam_side", "cam_top", "cam_wrist"]
TASK = "Place the red vial in position 3 of the right rack."

FRAME_FRAC = 0.05
NEAR_EP = int(sys.argv[1]) if len(sys.argv) > 1 else 49
FAR_EP = int(sys.argv[2]) if len(sys.argv) > 2 else 95


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
ep_idx = np.array(ds.hf_dataset["episode_index"])
state_all = np.stack(ds.hf_dataset["observation.state"]).astype(float)
# Works with EITHER dataset: EE (7D) used as-is, joint (6D) converted via FK.
IS_EE = state_all.shape[1] == 7
print(f"dataset state dim = {state_all.shape[1]} -> {'EE (direct)' if IS_EE else 'joint (FK to EE)'}")


def ee_pos(row):
    row = np.asarray(row, float)
    return row[:3] if IS_EE else kin.forward_kinematics(row)[:3, 3]

with safe_open(f"{CKPT}/policy_postprocessor_step_0_unnormalizer_processor.safetensors", framework="pt") as h:
    A_MEAN = h.get_tensor("action.mean").float().numpy()
    A_STD = h.get_tensor("action.std").float().numpy()

policy, pre, post = load_policy_and_processors(CKPT, dev)

wp = json.loads(Path(JOINT_WAYPOINTS_PATH).read_text())
q_home = np.array(wp["above_vial"], float)
T = kin.forward_kinematics(q_home)
rot = Rotation.from_matrix(T[:3, :3]).as_rotvec()
HOME_STATE = np.array([T[0, 3], T[1, 3], T[2, 3], rot[0], rot[1], rot[2], float(q_home[5])], np.float32)


def true_grasp(ep):
    rows = np.where(ep_idx == ep)[0]
    half = rows[: int(0.6 * len(rows))]
    gg = state_all[half][:, -1]               # gripper is the last channel in both formats
    cand = np.where(gg > 25.0)[0]
    fi = cand[0] if len(cand) else int(np.argmax(gg))
    return ee_pos(state_all[half][fi])


def predict_grasp(ep):
    rows = np.where(ep_idx == ep)[0]
    idx = rows[int(FRAME_FRAC * len(rows))]
    item = ds[idx]
    obs = {"observation.state": HOME_STATE.copy()}
    for c in CAM_NAMES:
        t = item[f"observation.images.{c}"]
        obs[f"observation.images.{c}"] = (t.clamp(0, 1) * 255).byte().permute(1, 2, 0).contiguous().numpy()
    batch = pre(prepare_observation_for_inference(obs, dev, TASK))
    if hasattr(policy, "reset"):
        policy.reset()
    chunk = policy.predict_action_chunk(batch)[0].float().cpu().numpy()
    phys = chunk * A_STD + A_MEAN
    zi = int(np.argmin(phys[:, 2]))
    return phys[zi], float(phys[:, 6].max())


print(f"CKPT = {CKPT}\nNEAR = ep {NEAR_EP},  FAR = ep {FAR_EP},  fixed state = above_vial\n")
tn, tf = true_grasp(NEAR_EP), true_grasp(FAR_EP)
pn, gn = predict_grasp(NEAR_EP)
pf, gf = predict_grasp(FAR_EP)

print(f"{'scene':>6} | {'true grasp xy':>16} | {'PRED grasp xyz':>24} | {'pred max grip':>12}")
print("-" * 72)
print(f"{'NEAR':>6} | ({tn[0]:.3f}, {tn[1]:.3f})   | ({pn[0]:.3f}, {pn[1]:.3f}, {pn[2]:.3f}) | {gn:>10.1f}")
print(f"{'FAR':>6} | ({tf[0]:.3f}, {tf[1]:.3f})   | ({pf[0]:.3f}, {pf[1]:.3f}, {pf[2]:.3f}) | {gf:>10.1f}")

true_dx = tf[0] - tn[0]
pred_dx = pf[0] - pn[0]
print(f"\n  true Δx (far - near) = {true_dx:+.3f} m")
print(f"  PRED Δx (far - near) = {pred_dx:+.3f} m")
print("\nVERDICT:")
if pred_dx > 0.4 * true_dx and pred_dx > 0.03:
    print("  ✅ PASS — prediction tracks the vial. Vision is used. Scale up + go to robot.")
elif abs(pred_dx) < 0.02:
    print("  ❌ FAIL — predictions ~identical for near/far. Still blind.")
else:
    print("  ⚠ PARTIAL — weak tracking. Train longer / more data before the robot.")
