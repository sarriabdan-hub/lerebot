#!/usr/bin/env bash
# π0 LoRA fine-tuning on vial-sort-v1-ee — CORRECTED, confound-matched to the full-FT run.
#
# Fixes the 3 footguns that crippled the original ee/train_pi0_lora.sh:
#   1. lora_alpha was unset -> peft defaulted to 8, giving scaling alpha/r = 8/16 = 0.5x
#      (every adapter delta was halved). Now alpha=64, r=32 -> scaling 2.0x.
#   2. target_modules defaulted to Q/V + 5 projections only; the expert MLP feed-forward
#      blocks (where motion primitives live) were FROZEN. Now we also target the expert
#      mlp gate/up/down + k/o attention projections.
#   3. LR was the pi0 default 2.5e-5 (decaying to 2.5e-6). Now 1e-4, matching the full-FT.
# Also matches the full-FT confounds: batch 16, 30k steps, same data, frozen vision.
# And pipes to a log so the loss curve is actually captured this time.
#
# Run from the lerobot repo root:
#   bash ee/train_pi0_lora_fair.sh            # full ~5h run
#   STEPS=2500 OUTDIR=outputs/train/vial-sort-pi0-lora-diag bash ee/train_pi0_lora_fair.sh   # ~15min diagnostic

set -euo pipefail

STEPS="${STEPS:-30000}"
OUTDIR="${OUTDIR:-outputs/train/vial-sort-pi0-lora-fair}"
LOGFILE="${LOGFILE:-/tmp/lora_fair.log}"

# Expert attention (q/k/v/o) + expert MLP (gate/up/down) + the 5 action/state projections.
# Single-quoted: contains regex metacharacters | ( ).
TARGETS='(.*\.gemma_expert\..*\.self_attn\.(q|k|v|o)_proj|.*\.gemma_expert\..*\.mlp\.(gate_proj|up_proj|down_proj)|model\.(state_proj|action_in_proj|action_out_proj|action_time_mlp_in|action_time_mlp_out))'

lerobot-train \
  --dataset.repo_id sari-abdan/vial-sort-v1-ee \
  --dataset.root ./data/vial-sort-v1-ee \
  --policy.type pi0 \
  --policy.pretrained_path lerobot/pi0 \
  --policy.push_to_hub false \
  --policy.dtype bfloat16 \
  --policy.freeze_vision_encoder true \
  --policy.train_expert_only true \
  --policy.optimizer_lr 1e-4 \
  --policy.chunk_size 50 \
  --policy.n_action_steps 50 \
  --policy.max_state_dim 32 \
  --policy.max_action_dim 32 \
  --peft.method_type LORA \
  --peft.r 32 \
  --peft.lora_alpha 64 \
  --peft.target_modules "$TARGETS" \
  --batch_size 16 \
  --steps "$STEPS" \
  --eval_freq 5000 \
  --log_freq 100 \
  --save_freq 5000 \
  --output_dir "$OUTDIR" \
  2>&1 | tee "$LOGFILE"
