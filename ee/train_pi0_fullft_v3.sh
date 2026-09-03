#!/usr/bin/env bash
# π0 full-FT v3 — the LANGUAGE-GROUNDING run. Warm-start from base_v1, on the
# clean current-pose subset (vial-sort-v3-ee, episodes that survived deleting the
# old-pose 0-41) with PARAPHRASED instructions (ee/paraphrase_tasks.py).
#
# WHY THIS DIFFERS FROM v2:
#   1. PARAPHRASED prompts. v1/v2 used ONE template -> the policy ignored language
#      (vision-shortcut failure: it drove to the named rack and grabbed air). Each
#      episode now has a distinct phrasing of the SAME (rack, position), forcing the
#      action expert to actually read "left/right" + the position number.
#   2. Clean data only: old-pose / blue-vial-inconsistent episodes 0-41 deleted.
#      Coverage = left pos 1/3/6 (full) + right pos 6. (Right 1/3 to be re-recorded.)
#   3. Vision frozen + train_expert_only (knowledge-insulating: protects the VLM's
#      language understanding from action-expert gradients — the documented π0 fix).
#   4. LONG run with FREQUENT saves so we eval the whole spectrum on the robot and
#      pick by REAL-ROBOT prompt-following, NOT loss. Expectation from the v1 overfit
#      lesson: the best checkpoint is likely EARLY (6k-15k), not 40k.
#
# Run from repo root (WS):  bash ee/train_pi0_fullft_v3.sh
#   STEPS=40000 SAVE=2000 bash ee/train_pi0_fullft_v3.sh   # (defaults)

set -euo pipefail

STEPS="${STEPS:-40000}"
SAVE="${SAVE:-2000}"
OUTDIR="${OUTDIR:-outputs/train/vial-sort-pi0-fullft-v3}"
LOGFILE="${LOGFILE:-/tmp/fullft_v3.log}"
BASE="${BASE:-outputs/train/vial-sort-pi0-fullft/checkpoints/last/pretrained_model}"

.venv/bin/lerobot-train \
  --dataset.repo_id sari-abdan/vial-sort-v3-ee \
  --dataset.root ./data/vial-sort-v3-ee \
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
  --save_freq "$SAVE" \
  --eval_freq "$SAVE" \
  --log_freq 100 \
  --output_dir "$OUTDIR" \
  2>&1 | tee "$LOGFILE"

# NEXT: deploy several checkpoints to Thor and eval prompt-following on the robot.
#   rsync "$OUTDIR"/checkpoints/<step>/pretrained_model/ robot@192.168.123.198:/home/robot/dev/lerebot/ckpt_v3_<step>/
# Test: vial on LEFT say "right pos 6" -> grabs LEFT first, places right 6.
#       vial on RIGHT say "left pos 1/3/6" -> grabs RIGHT first, places the named left slot.
# Pick the checkpoint that FOLLOWS THE PROMPT best, NOT the lowest loss.
