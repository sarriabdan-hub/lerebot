#!/usr/bin/env bash
# π0 full-FT retrain v2 — WARM-START from base_v1, on old (pos-3) + new (varied) data.
#
# WHY this differs from the first fullft:
#   1. WARM START from base_v1 (the existing fullft), NOT raw lerobot/pi0. base_v1 is
#      already adapted to our robot/cameras/joint-space; we only need to teach the new
#      camera pose + varied destinations on top, so far fewer steps are needed.
#   2. Train on the FRESH v2 dataset ALONE. v1 is correctly labeled (source = left 1/3/4/5,
#      destination = ALWAYS right pos 3) but it only adds ONE destination (right-3) at the OLD
#      camera pose — and v2's right-pos-3 anchor session already reproduces that at the correct
#      new pose with the same source variety. So v1 is redundant here, not harmful; skip it.
#      base_v1's weights carry the pickup priors via warm start, so no replay is needed.
#   3. IMAGE AUGMENTATION on: --dataset.image_transforms.enable true turns on the default
#      transforms incl. an `affine` one (+-5 deg, +-5% translate) that SIMULATES A BUMPED
#      CAMERA every step, plus brightness/contrast/hue/sharpness for lighting. This is the
#      systematic way to "teach the model the camera might shift".
#   3. FEW steps + FREQUENT saves. The first run was driven to 30k / loss 0.030 and
#      OVERFIT (15k and even the 6k divtest placed as well or better on the real robot).
#      So we stop early and pick the best checkpoint by ROBOT EVAL, not lowest loss.
#
# PREREQ: pull the recorded v2 dataset locally to ./data/vial-sort-v2-ee
#
# Run from the lerobot repo root (workstation / Blackwell):
#   bash ee/train_pi0_fullft_v2.sh
#   STEPS=4000 OUTDIR=outputs/train/vial-sort-pi0-fullft-v2-diag bash ee/train_pi0_fullft_v2.sh  # quick diag

set -euo pipefail

STEPS="${STEPS:-12000}"
OUTDIR="${OUTDIR:-outputs/train/vial-sort-pi0-fullft-v2}"
LOGFILE="${LOGFILE:-/tmp/fullft_v2.log}"
# base_v1 = the existing fullft we are continuing from.
BASE="${BASE:-outputs/train/vial-sort-pi0-fullft/checkpoints/last/pretrained_model}"

.venv/bin/lerobot-train \
  --dataset.repo_id sari-abdan/vial-sort-v2-ee \
  --dataset.root ./data/vial-sort-v2-ee \
  --dataset.image_transforms.enable true \
  --policy.type pi0 \
  --policy.pretrained_path "$BASE" \
  --policy.push_to_hub false \
  --policy.dtype bfloat16 \
  --policy.freeze_vision_encoder true \
  --policy.train_expert_only true \
  --policy.optimizer_lr 1e-4 \
  --policy.chunk_size 50 \
  --policy.n_action_steps 50 \
  --policy.max_state_dim 32 \
  --policy.max_action_dim 32 \
  --batch_size 16 \
  --steps "$STEPS" \
  --save_freq 1500 \
  --eval_freq 1500 \
  --log_freq 100 \
  --output_dir "$OUTDIR" \
  2>&1 | tee "$LOGFILE"

# NEXT: deploy SEVERAL checkpoints (e.g. 6000, 9000, 12000) and eval on the robot —
#   rsync "$OUTDIR"/checkpoints/<step>/pretrained_model/ robot@192.168.123.198:/home/robot/dev/lerebot/ckpt_v2_<step>/
#   then ee/vla_server.py --checkpoint .../ckpt_v2_<step>  and run the eval sheet.
# Pick the checkpoint with the best real-robot success rate, NOT the lowest train loss.
