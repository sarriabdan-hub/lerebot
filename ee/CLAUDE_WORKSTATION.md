# CLAUDE_WORKSTATION.md — Workstation context

Read CLAUDE.md (repo root) first, then this file.

---

## Current state (as of 2026-06-11)

Two trainings (30k/100ep and a 5k/5ep LoRA test) both failed 0/10 on the robot, behaving
identically. Offline diagnosis (2026-06-11) traced it to the **LoRA fine-tune being far too
weak to learn the task** — the model barely changed from base π0. The vision-tower loader
bug was real but is NOT the cause (and is a no-op under PEFT anyway). See diagnosis below.
The fix is a proper fine-tune config, not more data.

### Diagnosis — CONFIRMED 2026-06-11 (it is the LoRA training config, nothing else)
Ran the policy offline on REAL recorded training frames (`ee/diagnose_policy.py`) and on
base π0 (`ee/base_check.py`). Findings:
- **IK is fine** — `trajectory_test.py` ALL PASS through the same pipeline.
- **FK/EE observation is fine** — matches probed waypoints to 4 decimals.
- **Inference path is fine** — verified the policy receives valid, *differing* images
  (real vs zero Δ≈450k), language is tokenized (48 tokens), and `config.image_features`
  matches the camera keys exactly (`cam_top/cam_wrist/cam_side`), 224² res, MEAN_STD norm.
- **The fine-tuned model cannot reproduce its own training trajectories.** Fed real frames
  spanning an episode, predicted z stays ≈0.15 and grip ≈10 (the dataset mean) while the
  true action sweeps z 0.10→0.30, grip 0→9, x 0.02→0.34. Output ≈ **base π0** — the LoRA
  barely changed the model.

**Root cause = the LoRA fine-tune was far too weak to learn the task:**
1. `adapter_config.json` had **r=16, alpha=8 → 0.5× scaling** (adapter effect halved; want alpha ≥ r).
2. Target modules were narrow: only `gemma_expert self_attn q/v_proj` + a few projections —
   **no k/o_proj, no MLP, and nothing on the PaliGemma VLM**, so vision grounding never adapted.
3. `lr = 2.5e-5` — too low for so few trainable params.
4. **`--policy.freeze_vision_encoder false` is a NO-OP under PEFT** — PEFT freezes everything
   that isn't an adapter, so vision was frozen in both runs regardless of the flag. The
   "unfreeze vision" change did nothing; that's why the retrain behaved identically.

→ The fix is NOT more data and NOT the vision-tower loader. It is a real fine-tune (below).

### ⚠️ Gripper: do NOT chase 100/100 in new demos
The source dataset `gripper.pos` (RANGE_0_100 scale) is:
```
min 0.0   max 46.28   mean 9.64
```
**46 IS "fully closed" for this arm's calibration.** You recorded the follower's position
with the leader squeezed shut and it tops out at 46 — the calibrated range is wider than the
physical travel, so 100 is physically unreachable. The gripper fails at inference because the
blind model never learned to command 46 at grasp time, NOT because the demos are "too open."
Earlier notes saying "ensure gripper closes 100/100" are wrong — ignore them. Fix vision and
the grip timing follows.

---

## Step 1 — Apply the vision tower fix (do this first, 2 min)

File: `lerobot/src/lerobot/policies/pi0/modeling_pi0.py`

Find the function `_fix_pytorch_state_dict_keys` and locate this block:
```python
if "patch_embedding" in key:
    logging.warning(f"Vision embedding key might need handling: {key}")
```

Replace it with:
```python
if "vision_tower.vision_model." in new_key:
    new_key = new_key.replace("vision_tower.vision_model.", "vision_tower.")
```

**Verify the fix works:**
```bash
python - <<'EOF'
import sys; sys.path.insert(0, "lerobot/src")
import warnings; warnings.filterwarnings("ignore")
import logging; logging.disable(logging.WARNING)
import io
from contextlib import redirect_stdout
from lerobot.configs.policies import PreTrainedConfig
from lerobot.policies.pi0 import PI0Policy

buf = io.StringIO()
with redirect_stdout(buf):
    cfg = PreTrainedConfig.from_pretrained("lerobot/pi0")
    PI0Policy.from_pretrained("lerobot/pi0", config=cfg)
out = buf.getvalue()
print("PASS" if "All keys loaded successfully!" in out else "FAIL — check the fix")
print(out[-300:])
EOF
```

Expected: `PASS` and `All keys loaded successfully!`

---

## Step 2 — Overfit test train (5 episodes) with a REAL fine-tune

Goal: prove the model can memorize 5 episodes. The previous LoRA was too weak (see
diagnosis). Use a **full fine-tune of the action expert** (no LoRA) — the 97GB GPU handles
the ~300M action expert easily, and it removes all LoRA-capacity guesswork.

```bash
lerobot-train \
  --dataset.repo_id sari-abdan/vial-sort-v1-ee \
  --dataset.root ./data/vial-sort-v1-ee \
  --dataset.episodes "[0,1,2,3,4]" \
  --policy.type pi0 \
  --policy.push_to_hub false \
  --policy.pretrained_path lerobot/pi0 \
  --policy.dtype bfloat16 \
  --policy.freeze_vision_encoder true \
  --policy.train_expert_only true \
  --policy.optimizer_lr 1e-4 \
  --policy.chunk_size 50 \
  --policy.n_action_steps 50 \
  --batch_size 8 \
  --steps 20000 \
  --save_freq 5000 \
  --output_dir outputs/train/vial-sort-pi0-overfit5b
```

⚠️ **LR GOTCHA (this bit us):** π0's LR field is `policy.optimizer_lr` (default 2.5e-5).
`--optimizer.lr 1e-4` is **silently ignored** — the run trains at 2.5e-5 anyway. You MUST use
`--policy.optimizer_lr 1e-4`. Verify after starting:
`grep optimizer_lr outputs/train/<run>/checkpoints/*/pretrained_model/train_config.json` → must read 1e-4.

What changed vs the broken runs, and WHY:
- **No `--peft.*`** → full fine-tune (LoRA r16/alpha8 = 0.5× scaling, vision frozen-by-PEFT).
  `train_expert_only true` trains the ~300M action expert fully; `freeze_vision_encoder true`
  keeps SigLIP frozen (OK for an overfit — the model can memorize 5 trajectories from state alone).
- **`--policy.optimizer_lr 1e-4`** — the first full-FT run used 2.5e-5 (flag ignored) + only 3000
  steps → undertrained. Loss hit 0.036 but the model never learned to condition: at inference it
  output a fixed ~mean pose (z≈0.16), never descended to grasp (z=0.078), and ignored vision.
- **`--steps 20000`** on 5 episodes (~36 epochs) to truly memorize.

WATCH THE LOSS: it must fall **well below 0.01** (0.036 is NOT enough — that's just the gross
average; flow-matching needs a tight fit to regenerate trajectories).

If VRAM is tight (won't be at 97GB), strong-LoRA alternative:
`--peft.method_type LORA --peft.r 32 --peft.lora_alpha 64 --policy.optimizer_lr 1e-4`
and broaden `--peft.target_modules` to the PaliGemma attention + gemma_expert MLP.

---

## Step 3 — VALIDATION GATE (do this BEFORE touching the robot)

The robot is slow and frustrating to debug on. Validate offline first. Sync the checkpoint
to Thor and run the same diagnostic that found the bug:

```bash
rsync -av outputs/train/vial-sort-pi0-overfit5/checkpoints/last/pretrained_model/ \
  robot@192.168.123.198:/home/robot/dev/lerebot/pretrained_model/
```
Use `rsync -av --delete ...` so stale files (old adapter_config.json) are removed — otherwise
the loader sees a leftover adapter and loads the WRONG model. On Thor, run BOTH gates:
```bash
/home/robot/miniforge3/envs/lerobot/bin/python ee/diagnose_policy.py   # step-0 action vs truth
/home/robot/miniforge3/envs/lerobot/bin/python ee/chunk_check.py       # full 50-step chunk
```
**PASS criteria:**
- `diagnose_policy.py`: predicted `z` TRACKS true `z` (descends across the episode, not stuck
  at 0.15); predicted grip rises where true grip rises; real-vs-zero image output DIFFERS.
- `chunk_check.py`: within-chunk normalized `z` must reach the grasp depth (≈ −1.9 normalized,
  i.e. ~0.078 m), NOT hover at −0.4 (~0.16 m); and real-img vs zero-img Δ must be clearly
  LARGER than the sampling noise.

Episodes 0–4 are in the training set, so a properly overfit model MUST reproduce them. Only
if both gates pass do you run the robot:
```bash
sudo chmod 666 /dev/ttyACM0
python ee/rollout_pi0_lora.py --trials 3 --duration 60 --visualize
```

If `diagnose_policy.py` still shows a flat ~mean prediction after a full-FT overfit run,
the problem is deeper than config (e.g. flow-matching / data label issue) — report the
table, do NOT collect more data.

---

## Step 4 — Decision after Thor test

| Thor result | Next action |
|---|---|
| Arm descends + gripper reaches ~46 at grasp | **Diagnosis confirmed** — collect 200+ demos, full 50k retrain |
| Red cross now tracks vial but misses | Model is learning — retrain with all 100 eps, 30k steps |
| Still hovering at z≈0.25, grip≈14 with vision loaded+unfrozen | NOT vision — escalate to action-space angle: absolute EE + `as_rotvec()` orientation discontinuity, check normalization stats |

Note: "gripper reaches ~46" = closed (see the gripper warning above). Do not expect 100.

---

## Full retrain command (after test passes)

```bash
lerobot-train \
  --dataset.repo_id sari-abdan/vial-sort-v1-ee \
  --dataset.root ./data/vial-sort-v1-ee \
  --policy.type pi0 \
  --policy.push_to_hub false \
  --policy.pretrained_path lerobot/pi0 \
  --policy.dtype bfloat16 \
  --policy.freeze_vision_encoder false \
  --policy.train_expert_only false \
  --policy.chunk_size 50 \
  --policy.n_action_steps 50 \
  --peft.method_type LORA \
  --peft.r 16 \
  --batch_size 8 \
  --steps 50000 \
  --eval_freq 5000 \
  --log_freq 100 \
  --save_freq 5000 \
  --output_dir outputs/train/vial-sort-pi0-lora-v2
```

---

## Dataset location

```
./data/vial-sort-v1-ee/     ← EE-space (7D actions) — use this for training
./data/vial-sort-v1-static/ ← joint-space original — do not use for π0
```

HuggingFace: `sari-abdan/vial-sort-v1-ee` (100 episodes, 65k frames)
