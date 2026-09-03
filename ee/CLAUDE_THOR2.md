# Claude Code — Jetson Thor, step 2

Read this before doing anything. This continues from `CLAUDE_THOR.md`.

---

## What happened before you (why step 1 failed)

The first model (30 000 steps, 100 episodes) failed the smoke test **0 / 10** on Thor.

**Root cause**: training used `--policy.freeze_vision_encoder true`.  
The vision encoder weights loaded correctly, but were frozen — the model never adapted to the
specific visual appearance of this scene (vials, racks, lighting).  The policy learned to map
state → actions but effectively ignored the image input.

**Fix**: retrain with `--policy.freeze_vision_encoder false` so the LoRA adapter can learn
to use visual features from *this* scene.  A **5-episode quick test train** (5 000 steps)
was run to verify the approach before committing to a full 50k retrain.  That checkpoint
was synced here.

---

## Checkpoint location on Thor

```
/home/robot/dev/lerebot/pretrained_model/
```

(Synced from workstation via `rsync ... robot@192.168.123.198:/home/robot/dev/lerebot/pretrained_model/`)

---

## Your tasks (in order)

### 1. Dry-run — confirm load + latency

```bash
cd ~/lerobot
source .venv/bin/activate   # adjust if using conda
pip install peft             # if not already installed

python ee/rollout_pi0_lora.py \
  --checkpoint /home/robot/dev/lerebot/pretrained_model \
  --dry-run
```

Expected: prints latency numbers, **no** `KeyError` or shape mismatch.  
If it crashes → copy the full traceback and report back to the workstation Claude.

### 2. Verify cameras and robot port

```bash
ls /dev/ttyACM*
lerobot-find-cameras
ls /dev/v4l/by-path/
rs-enumerate-devices          # confirm serial 052622071016
ls /home/robot/dev/lerebot/calibration/robots/so_follower/
```

If camera paths or calibration dir differ from what's in `ee/rollout_pi0_lora.py`, edit:
- Lines ~115-119: `cam_top` / `cam_wrist` index_or_path strings
- Line ~133: `calibration_dir=Path(...)`

### 3. Real-robot smoke test — 3 trials

```bash
sudo chmod 666 /dev/ttyACM0

python ee/rollout_pi0_lora.py \
  --checkpoint /home/robot/dev/lerebot/pretrained_model \
  --trials 3 \
  --duration 60 \
  --visualize
```

`--visualize` opens an OpenCV window showing all 3 cameras side-by-side.  
Drop it if Thor is headless (or SSH with `-X`).

**This is a sanity check — the 5-episode model won't place vials correctly.**  
What you want to see:

| | What to look for |
|---|---|
| ✅ Good | Arm moves toward the vial; grip opens/closes |
| ⚠️ Weak | Arm moves but hovers, doesn't grip |
| ❌ Bad | Arm frozen, or IK / FK crash |

Enter results when prompted. Results saved to `ee/smoke_test_log.csv`.

### 4. Report back

After step 4, tell the workstation Claude:
- Did dry-run load cleanly? (yes / no + traceback if no)
- Thor latency mean and p95
- Did the arm move during the 3 trials? (yes / no)
- Which row in the table above matches what you saw?

The workstation Claude will then kick off the full retrain (50 000 steps, all 100 episodes)
based on what you report.

---

## What happens next (decision table from workstation)

| Thor result | Next action |
|---|---|
| Arm grips vial at least once | Collect 200+ more demos → retrain 50k steps |
| Arm tracks vial but misses | Retrain with all 100 eps, 30k steps |
| Still hovering, grip=14, frozen | IK / EE pipeline issue — investigate before more training |

---

## Key commands

```bash
# Dry-run
python ee/rollout_pi0_lora.py --checkpoint /home/robot/dev/lerebot/pretrained_model --dry-run

# Smoke test
sudo chmod 666 /dev/ttyACM0
python ee/rollout_pi0_lora.py --checkpoint /home/robot/dev/lerebot/pretrained_model --trials 3 --duration 60 --visualize

# Manual teleoperation (verify arm moves without policy)
python ee/teleoperate.py
```

---

## Watch-outs

- **`--visualize` needs a display**: headless → SSH with `-X`, or drop the flag.
- **5-episode model won't grasp well**: that's expected — this run is just proving the fix works.
- **`MAX_EE_STEP_M = 0.05`** (5 cm/tick safety cap): if arm looks frozen but inference runs, try raising to 0.08 in `rollout_pi0_lora.py` line ~65.
- **HF cache**: `lerobot/pi0` base weights must be in `~/.cache/huggingface/hub/`. First run downloads ~4 GB.
