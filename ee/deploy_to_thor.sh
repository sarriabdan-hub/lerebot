#!/usr/bin/env bash
# Transfer the LoRA checkpoint + ee/ scripts to Jetson Thor.
#
# Usage (from workstation, lerobot repo root):
#   bash ee/deploy_to_thor.sh [thor-hostname-or-ip]
#
# The script assumes:
#   - Thor is reachable via SSH as `robot@<host>`
#   - lerobot is cloned at ~/lerobot on Thor
#   - The HF cache (~/.cache/huggingface) on Thor already has lerobot/pi0
#     (or Thor has internet access to download it on first run)

set -euo pipefail

THOR="${1:-192.168.123.198}"
REMOTE="robot@${THOR}"
REMOTE_ROOT="~/lerobot"

echo "=== Syncing LoRA checkpoint ==="
rsync -av --progress \
  outputs/train/vial-sort-pi0-lora/checkpoints/last/pretrained_model/ \
  "${REMOTE}:${REMOTE_ROOT}/outputs/train/vial-sort-pi0-lora/checkpoints/last/pretrained_model/"

echo ""
echo "=== Syncing ee/ scripts ==="
rsync -av --progress \
  ee/ \
  "${REMOTE}:${REMOTE_ROOT}/ee/"

echo ""
echo "=== Syncing SO101 URDF ==="
rsync -av --progress \
  SO101/ \
  "${REMOTE}:${REMOTE_ROOT}/SO101/"

echo ""
echo "Done. On Thor, run:"
echo "  cd ~/lerobot"
echo "  python ee/rollout_pi0_lora.py --dry-run          # latency check"
echo "  python ee/rollout_pi0_lora.py --trials 10        # smoke test"
