#!/usr/bin/env bash
# π0 LoRA fine-tuning on vial-sort-v1-ee.
#
# Run from the lerobot repo root:
#   bash ee/train_pi0_lora.sh

set -euo pipefail

lerobot-train \
  --dataset.repo_id sari-abdan/vial-sort-v1-ee \
  --dataset.root ./data/vial-sort-v1-ee \
  --policy.type pi0 \
  --policy.pretrained_path lerobot/pi0 \
  --policy.push_to_hub false \
  --policy.dtype bfloat16 \
  --policy.freeze_vision_encoder true \
  --policy.train_expert_only false \
  --policy.chunk_size 50 \
  --policy.n_action_steps 50 \
  --policy.max_state_dim 32 \
  --policy.max_action_dim 32 \
  --peft.method_type LORA \
  --peft.r 16 \
  --batch_size 8 \
  --steps 30000 \
  --eval_freq 5000 \
  --log_freq 100 \
  --save_freq 5000 \
  --output_dir outputs/train/vial-sort-pi0-lora
