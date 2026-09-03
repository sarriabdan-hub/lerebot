#!/usr/bin/env bash
# GR00T N1.5 fine-tune v5 — the A/B hedge vs pi0.5-v5, on the SAME RGB data.
#
# KEY DIFFERENCE FROM v4: vision is FROZEN (--policy.tune_visual false).
#   v4 set tune_visual=true (unfrozen) and OVERFIT -> "grabbed nothing" (OOD).
#   NVIDIA's own default is tune_visual=False. Freezing it: (1) fixes the overfit,
#   (2) makes a FAIR A/B vs pi0.5 (both frozen vision), (3) trains lighter/faster.
#
# Same dataset pi0.5-v5 used (vial-sort-v5-ee-rgb, 150 eps, RGB-only, position labels)
# so the ONLY variable is the model. batch 16 to match pi0.5-v5.
#
# PREREQ (already satisfied on this WS from the v4 run): pip install -e ".[groot]"
#   + the SDPA no-flash-attn patch to eagle2_5_vl.  Nothing new to install.
#
# Run from repo root (WS), in tmux:
#   tmux new -s groot
#   bash ee/train_groot_v5.sh
#   (detach: Ctrl-b then d   |   reattach: tmux attach -t groot)

set -euo pipefail

STEPS="${STEPS:-20000}"
SAVE="${SAVE:-2000}"
BATCH="${BATCH:-16}"
REPO="${REPO:-sari-abdan/vial-sort-v5-ee-rgb}"
ROOT="${ROOT:-./data/vial-sort-v5-ee-rgb}"
OUTDIR="${OUTDIR:-outputs/train/vial-sort-groot-v5}"
LOGFILE="${LOGFILE:-/tmp/groot_v5.log}"

# guard: RGB-only (no cam_depth), same as pi0.5
.venv/bin/python - "$ROOT" <<'PY'
import json, sys
imgs = [k for k in json.load(open(f"{sys.argv[1]}/meta/info.json"))["features"] if "image" in k]
print("image streams:", imgs)
assert not any("cam_depth" in k for k in imgs), "cam_depth present -> use the RGB dataset."
print("OK: RGB-only")
PY

.venv/bin/lerobot-train \
  --dataset.repo_id "$REPO" \
  --dataset.root "$ROOT" \
  --dataset.image_transforms.enable true \
  --policy.type groot \
  --policy.push_to_hub false \
  --policy.tune_llm false \
  --policy.tune_visual false \
  --policy.tune_projector true \
  --policy.tune_diffusion_model true \
  --policy.embodiment_tag new_embodiment \
  --batch_size "$BATCH" \
  --steps "$STEPS" \
  --save_freq "$SAVE" \
  --eval_freq "$SAVE" \
  --log_freq 100 \
  --output_dir "$OUTDIR" \
  2>&1 | tee "$LOGFILE"

# NOTES:
# - base_model_path defaults to nvidia/GR00T-N1.5-3B in the config.
# - GR00T pads state/action internally (max_state_dim=64/action=32); our 7-D EE fits.
#   Do NOT pass pi05's max_*_dim flags here.
# - Deploy with --n-action-steps 16. Pick the checkpoint by ROBOT eval, not loss.
