#!/usr/bin/env bash
# π0.5 fine-tune v4 — the FRESH start on the densified 3-destination dataset.
#
# WHY THIS DIFFERS FROM v2/v3:
#   1. BASE MODEL = pi0.5 (policy.type=pi05), fine-tuned FROM lerobot/pi05_base — NOT a
#      warm-start from our pi0 base_v1. pi05 has stronger language grounding (the documented
#      LeRobot-supported upgrade; pi07 is not self-hostable in LeRobot). Different architecture
#      family, so we start from pi05's own pretrained weights.
#   2. DATA = vial-sort-v4-merged-ee = the 78 existing paraphrased eps + 40 NEW eps, so each of
#      the 3 destinations (left p1, left p6, right p6) now has ~33 demos. THE real fix: dense
#      data per destination (SO-101+pi0 curve: ~100 eps/task -> ~70%). New eps also include a
#      moving BLUE distractor vial for clutter generalization.
#   3. Frozen vision + image augmentation kept (camera-shift / lighting robustness, +-5%).
#   4. FEW steps, FREQUENT saves — pick the checkpoint by REAL-ROBOT prompt-following + first-try
#      grasp, NOT lowest loss (v1 overfit lesson: 30k was worse than 6k/15k).
#
# PREREQ (see ee/RECORDING_SHEET_v4.txt): record 40 eps -> convert -> paraphrase the NEW set ->
#   ee/merge_v4.py  => data/vial-sort-v4-merged-ee must exist locally.
#
# Run from repo root (WS):  bash ee/train_pi05_v4.sh
#   STEPS=15000 bash ee/train_pi05_v4.sh   # (defaults)

set -euo pipefail

STEPS="${STEPS:-30000}"
SAVE="${SAVE:-2000}"
OUTDIR="${OUTDIR:-outputs/train/vial-sort-pi05-v4}"
LOGFILE="${LOGFILE:-/tmp/pi05_v4.log}"
BASE="${BASE:-lerobot/pi05_base}"   # pi0.5 pretrained base from HF (auto-downloaded)

.venv/bin/lerobot-train \
  --dataset.repo_id sari-abdan/vial-sort-v4-merged-ee \
  --dataset.root ./data/vial-sort-v4-merged-ee \
  --dataset.image_transforms.enable true \
  --policy.type pi05 \
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
  --save_freq "$SAVE" \
  --eval_freq "$SAVE" \
  --log_freq 100 \
  --output_dir "$OUTDIR" \
  2>&1 | tee "$LOGFILE"

# NOTE: if pi05 rejects --policy.train_expert_only, drop that flag (keep freeze_vision_encoder).
# NEXT: deploy checkpoints (e.g. 6k/9k/12k/15k), run vla_server.py with the FIXED HOME_POSE
#   and --n-action-steps 8-12, eval prompt-following + FIRST-TRY grasp. Pick by robot, not loss.
#   rsync "$OUTDIR"/checkpoints/<step>/pretrained_model/ robot@192.168.123.198:/home/robot/dev/lerebot/ckpt_v4_<step>/
