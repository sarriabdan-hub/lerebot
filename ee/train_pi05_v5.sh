#!/usr/bin/env bash
# π0.5 fine-tune v5 — RGB-ONLY, position-grammar dataset (150 eps).
#
# Same proven recipe as train_pi05_v4.sh (frozen vision, train_expert_only,
# batch 16), but on the v5 EE + position-relabeled data with cam_depth REMOVED.
#
# WHY a separate RGB dataset: lerobot-train auto-uses EVERY observation.images.*
# in the dataset (factory.py builds input_features from all non-action features);
# there is no CLI flag to drop one camera. So we train on a copy that has only the
# 3 RGB streams. Depth stays in vial-sort-v5-ee as reference.
#
# PREREQ (one-time, see the RGB-prep block in chat): create
#   ./data/vial-sort-v5-ee-rgb  via  lerobot-edit-dataset remove_feature cam_depth.
#
# Run from repo root (WS), inside tmux:
#   tmux new -s pi05
#   bash ee/train_pi05_v5.sh
#   (detach: Ctrl-b then d   |   reattach: tmux attach -t pi05)

set -euo pipefail

STEPS="${STEPS:-30000}"
SAVE="${SAVE:-2000}"
REPO="${REPO:-sari-abdan/vial-sort-v5-ee-rgb}"
ROOT="${ROOT:-./data/vial-sort-v5-ee-rgb}"
OUTDIR="${OUTDIR:-outputs/train/vial-sort-pi05-v5}"
LOGFILE="${LOGFILE:-/tmp/pi05_v5.log}"
BASE="${BASE:-lerobot/pi05_base}"

# hard guard: refuse to train if cam_depth is still present (would silently train +depth)
.venv/bin/python - "$ROOT" <<'PY'
import json, sys
feats = json.load(open(f"{sys.argv[1]}/meta/info.json"))["features"]
imgs = [k for k in feats if "image" in k]
print("image streams:", imgs)
assert not any("cam_depth" in k for k in imgs), \
    "cam_depth still present -> run the remove_feature step first (RGB-only aborted)."
print("OK: RGB-only (no cam_depth)")
PY

.venv/bin/lerobot-train \
  --dataset.repo_id "$REPO" \
  --dataset.root "$ROOT" \
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

# If pi05 rejects --policy.train_expert_only, drop that ONE flag (keep freeze_vision_encoder).
# NEXT: deploy checkpoints (6k/9k/12k/15k), vla_server --n-action-steps 15, eval prompt-follow
#       + first-try grasp on the ROBOT. Pick by robot, not loss.
