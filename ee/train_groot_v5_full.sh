#!/usr/bin/env bash
# GR00T N1.5 fine-tune v5 — UNFROZEN VISION ("full") run, tuned for best quality
# on small data. This is the head-to-head partner for ee/train_groot_v5.sh (frozen).
#
# WHAT'S UNFROZEN:  --policy.tune_visual true   (the vision encoder trains)
# WHAT STAYS FROZEN: --policy.tune_llm false    (ON PURPOSE — training the language
#   model on 150 eps causes catastrophic forgetting of language, which DESTROYS
#   prompt-following. Freezing the LLM protects the exact thing you want. Do NOT flip
#   this to true unless you want to lose prompt-following.)
#
# TUNED FOR SMALL-DATA UNFROZEN (differs from v4's naive unfrozen run):
#   - SAVE every 1000 steps: unfrozen vision peaks EARLY (≈4k-8k) then overfits, and we
#     must not miss the best one between saves.
#   - STEPS 15000: no point running long past the early peak.
#   - image augmentation ON: the main defense against vision overfitting.
#   - batch 16: unfrozen fits ~55 GB; batch 32 OOMs on the 96 GB card. Batch is not a
#     quality dial anyway (smaller often generalizes better).
#
# Same RGB dataset pi0.5-v5 + frozen-GR00T use, so it's a clean 3-way A/B.
#
# Run from repo root (WS), in tmux:
#   tmux new -s grootfull
#   bash ee/train_groot_v5_full.sh
#   (detach: Ctrl-b then d  |  reattach: tmux attach -t grootfull)

set -euo pipefail

STEPS="${STEPS:-15000}"
SAVE="${SAVE:-1000}"
BATCH="${BATCH:-16}"
REPO="${REPO:-sari-abdan/vial-sort-v5-ee-rgb}"
ROOT="${ROOT:-./data/vial-sort-v5-ee-rgb}"
OUTDIR="${OUTDIR:-outputs/train/vial-sort-groot-v5-full}"
LOGFILE="${LOGFILE:-/tmp/groot_v5_full.log}"

.venv/bin/python - "$ROOT" <<'PY'
import json, sys
imgs = [k for k in json.load(open(f"{sys.argv[1]}/meta/info.json"))["features"] if "image" in k]
assert not any("cam_depth" in k for k in imgs), "cam_depth present -> use the RGB dataset."
print("OK: RGB-only", imgs)
PY

.venv/bin/lerobot-train \
  --dataset.repo_id "$REPO" \
  --dataset.root "$ROOT" \
  --dataset.image_transforms.enable true \
  --policy.type groot \
  --policy.push_to_hub false \
  --policy.tune_llm false \
  --policy.tune_visual true \
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

# Deploy with --n-action-steps 16. Pick the checkpoint by ROBOT eval, not loss.
# Because vision is unfrozen, eval the EARLY checkpoints first (4k/6k/8k) — the peak
# is usually there, before overfitting.
