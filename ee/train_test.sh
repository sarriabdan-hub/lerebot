#!/usr/bin/env bash
# Quick 5-episode test train to verify the vision-key fix.
# ~10 min on RTX 6000. Output: outputs/train/vial-sort-pi0-lora-test
#
# Run from the lerobot repo root:
#   bash ee/train_test.sh

set -euo pipefail

lerobot-train \
  --dataset.repo_id sari-abdan/vial-sort-v1-ee \
  --dataset.root ./data/vial-sort-v1-ee \
  --dataset.episodes "[0,1,2,3,4]" \
  --policy.type pi0 \
  --policy.push_to_hub false \
  --policy.pretrained_path lerobot/pi0 \
  --policy.dtype bfloat16 \
  --policy.freeze_vision_encoder false \
  --policy.chunk_size 50 \
  --policy.n_action_steps 50 \
  --policy.max_state_dim 32 \
  --policy.max_action_dim 32 \
  --peft.method_type LORA \
  --peft.r 16 \
  --batch_size 8 \
  --steps 5000 \
  --save_freq 5000 \
  --log_freq 50 \
  --output_dir outputs/train/vial-sort-pi0-lora-test
