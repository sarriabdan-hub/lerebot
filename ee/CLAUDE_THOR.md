# Claude Code — Jetson Thor context

This file is for Claude Code running on **Jetson Thor** (`robot@192.168.123.198`).
Read this before doing anything.

---

## What this project is

Fine-tuning and deploying **π0 (pi-zero)** — a 4B-parameter VLA (Vision-Language-Action) model — on an **SO-101 robot arm** for a vial-sorting task.

Task: *"Place the red vial in position 3 of the right rack."*

Hardware on Thor:
- SO-101 follower arm on `/dev/ttyACM0`
- 3 cameras: `cam_top` (USB), `cam_wrist` (USB), `cam_side` (RealSense serial `052622071016`)
- Jetson Thor, ~60 GB unified memory

---

## Repo layout (on Thor: `~/lerobot`)

```
~/lerobot/
  ee/                          ← all project scripts
    rollout_pi0_lora.py        ← main inference script (run this)
    record.py                  ← data collection (already done)
    teleoperate.py             ← manual teleoperation check
    deploy_to_thor.sh          ← sync from workstation (already run)
    INFERENCE_PERF.md          ← latency doc (fill in after dry-run)
    smoke_test_log.csv         ← created automatically during trials
    SESSION_LOG.md             ← full history of what was done
  SO101/
    so101_new_calib.urdf       ← robot URDF for FK/IK
  outputs/train/vial-sort-pi0-lora/checkpoints/last/pretrained_model/
    adapter_model.safetensors  ← LoRA weights (5.4 MB)
    adapter_config.json        ← LoRA config (base: lerobot/pi0)
    policy_preprocessor*.json  ← normalizer stats from training
    policy_postprocessor*.json ← unnormalizer stats
```

---

## What has been done (on the workstation, before you)

1. ✅ Recorded 100 episodes (`sari-abdan/vial-sort-v1-ee`) — 7D EE-space actions, 3 cameras
2. ✅ Fine-tuned π0 with LoRA rank 16 — 30 000 steps, batch 8, bfloat16
3. ✅ Smoke-tested training (50 steps) — no crash, checkpoint saved
4. ✅ Written `ee/rollout_pi0_lora.py` — inference + FK/IK + latency measurement
5. ✅ Dry-run on workstation (RTX 6000): 4.6 ms latency, 28.5 Hz control loop

**You are here: deploy to Thor and run the real-robot smoke test.**

---

## Your tasks (in order)

### 1. Dry-run — verify load + latency, no robot needed

```bash
cd ~/lerobot
source <activate your venv>          # e.g. source .venv/bin/activate
pip install peft                     # if not already installed
python ee/rollout_pi0_lora.py \
  --checkpoint outputs/train/vial-sort-pi0-lora/checkpoints/last/pretrained_model \
  --dry-run
```

Expected output:
```
Device: cuda
Loading policy...   ← downloads lerobot/pi0 base (~4 GB) on first run — normal
Policy loaded.
[dry-run] Results over 10 s:
  Inference latency : X ms mean / X ms p95
  Control loop frequency : ~30 Hz
```

If it crashes with OOM → report back. If it loads fine → proceed.

Fill in the Thor numbers in `ee/INFERENCE_PERF.md`.

### 2. Verify cameras and robot port

```bash
# Check robot port
ls /dev/ttyACM*
sudo chmod 666 /dev/ttyACM0

# Check USB cameras
lerobot-find-cameras          # lists all cameras and their paths
# Verify /dev/v4l/by-path/ paths match what's in rollout_pi0_lora.py

# Check RealSense
rs-enumerate-devices          # verify serial 052622071016 appears
```

If camera paths on Thor differ from what's in `rollout_pi0_lora.py`, edit the script:
```python
# In ee/rollout_pi0_lora.py, function build_robot_and_pipelines()
"cam_top":   OpenCVCameraConfig(index_or_path="/dev/v4l/by-path/..."),  ← update here
"cam_wrist": OpenCVCameraConfig(index_or_path="/dev/v4l/by-path/..."),  ← and here
```

### 3. Real-robot smoke test — 10 trials

```bash
sudo chmod 666 /dev/ttyACM0
python ee/rollout_pi0_lora.py \
  --checkpoint outputs/train/vial-sort-pi0-lora/checkpoints/last/pretrained_model \
  --trials 10 \
  --duration 30
```

For each trial:
- Position a **fresh scenario** (vial not used in training if possible)
- Press Enter to start
- Watch for 30 s
- Enter result when prompted:
  - `0` = OK (success)
  - `1` = MissedGrip
  - `2` = DroppedVial
  - `3` = Collision
  - `4` = WrongRack
  - `5` = ABORT (Ctrl+C early)
  - `6` = OTHER

Results auto-saved to `ee/smoke_test_log.csv`.

### 4. Fill in the perf doc

After dry-run and smoke test, fill in `ee/INFERENCE_PERF.md`:
- Thor latency mean + p95
- Thor control frequency
- Smoke test summary (OK count / 10)

---

## Key commands reference

```bash
# Activate env
source ~/lerobot/.venv/bin/activate    # adjust if using conda

# Dry-run (no robot)
python ee/rollout_pi0_lora.py --checkpoint outputs/train/vial-sort-pi0-lora/checkpoints/last/pretrained_model --dry-run

# Smoke test (robot connected)
sudo chmod 666 /dev/ttyACM0
python ee/rollout_pi0_lora.py --checkpoint outputs/train/vial-sort-pi0-lora/checkpoints/last/pretrained_model --trials 10 --duration 30

# Manual teleoperation check (no policy)
python ee/teleoperate.py

# Check calibration files exist
ls ~/lerobot/calibration/robots/so_follower/
```

---

## Known watch-outs

- **HF base model download**: on first dry-run, `lerobot/pi0` base weights (~4 GB) will download from HuggingFace. Thor needs internet or a pre-staged HF cache. If no internet: copy the HF cache from the workstation (`~/.cache/huggingface/hub/models--lerobot--pi0/`) via rsync.
- **PaliGemma gate**: `google/paligemma-3b-pt-224` is gated. The HF token needs to be logged in AND the license accepted on `sari-abdan`'s HF account (already done on workstation). If Thor uses the same HF token (`~/.cache/huggingface/token`), it should work. If not: `huggingface-cli login` or `hf auth login` with the token.
- **Camera paths**: the `/dev/v4l/by-path/platform-a80aa10000...` paths are Jetson-specific. Confirm they exist with `ls /dev/v4l/by-path/` before running.
- **Max EE step**: `MAX_EE_STEP_M = 0.05` in the script limits per-step EE displacement to 5 cm for safety. If the arm seems sluggish, it can be raised slightly.
- **Action chunk**: π0 predicts 50 actions at once and dequeues 1 per tick. The arm will look smooth even if inference is slow — this is expected behaviour.
