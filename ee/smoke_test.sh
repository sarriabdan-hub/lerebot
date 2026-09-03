#!/usr/bin/env bash
# Smoke test — 50 steps on 10 episodes.
# Goal: confirm the pipeline doesn't crash and produces a saveable checkpoint.
#
# Run from the lerobot repo root:
#   bash ee/smoke_test.sh

set -euo pipefail

lerobot-train \
  --dataset.repo_id sari-abdan/vial-sort-v1-ee \
  --dataset.root ./data/vial-sort-v1-ee \
  --dataset.episodes "[0,1,2,3,4,5,6,7,8,9]" \
  --policy.type pi0 \
  --policy.push_to_hub false \
  --policy.pretrained_path lerobot/pi0 \
  --policy.dtype bfloat16 \
  --policy.freeze_vision_encoder true \
  --peft.method_type LORA \
  --peft.r 16 \
  --batch_size 4 \
  --steps 50 \
  --eval_freq 50 \
  --log_freq 10 \
  --save_freq 50 \
  --output_dir outputs/train/smoke_test

echo ""
echo "Smoke test done. Check checkpoint:"
echo "  ls outputs/train/smoke_test/checkpoints/"
