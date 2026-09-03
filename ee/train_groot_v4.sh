#!/usr/bin/env bash
# GR00T N1.5 fine-tune on the SAME v4 dataset — the head-to-head vs pi0.5-v4.
#
# WHY: one-run empirical answer to "is GR00T's language-following better for us?"
#   (VILAS benchmark says pi0.5 wins language 0.67 vs 0.40; community says GR00T's
#   language is strong — settle it on OUR data/robot. See PLAN_FABLE §7 / Papers #16.)
# Same data, same eval protocol as pi05-v4 => clean A/B:
#   - dataset: vial-sort-v4-merged-ee (118 eps, EE-space, paraphrased)
#   - base:    nvidia/GR00T-N1.5-3B (auto-download; EmbodimentTag=new_embodiment)
#   - recipe: LLM FROZEN (language grounding is the thing we're testing — don't
#     overwrite it with 118 single-domain episodes), VISION UNFROZEN (Sari's call:
#     97GB Blackwell has the room, and frozen-vision pixel-target memorization is
#     our documented failure mode — the camera-bump saga), projector + diffusion
#     action head trained. LoRA off.
#   - UNFROZEN-VISION CAVEAT: with only 118 eps the vision tower can memorize the
#     frames within a few k steps. Expect the BEST checkpoint EARLY (4k-8k), not
#     late — evaluate the early saves first, and keep image_transforms on (it's
#     the anti-memorization pressure).
#
# PREREQ (one-time): GR00T needs extra deps incl. flash-attn (compiles ~minutes):
#     .venv/bin/pip install -e ".[groot]"
#   If flash-attn fails to build: .venv/bin/pip install ninja && retry with
#     MAX_JOBS=8 .venv/bin/pip install flash-attn --no-build-isolation
#
# Run from repo root (WS):  bash ee/train_groot_v4.sh
#   STEPS=20000 bash ee/train_groot_v4.sh
#
# EVAL: checkpoints deploy through the SAME servers (vla_server.py --checkpoint <dir>
#   on Thor, or isaac/vla_sim_server.py in sim) — the loader picks the policy class
#   from the checkpoint config (get_policy_class), so no server changes needed.
#   Compare vs pi05-v4 on: prompt-following per destination, first-try grasp,
#   jitter_deg, and Robometer-scored success. Note GR00T's native chunk regime is
#   16-ish steps — start deployment with --n-action-steps 16.

set -euo pipefail

# "Whatever it takes" settings (Sari 2026-07-06): batch 32 (NVIDIA's own default —
# 97GB Blackwell takes it easily; better gradient estimates than 16), checkpoints
# every 1000 steps (unfrozen vision peaks EARLY and we don't want to miss the best
# one between saves; disk is cheap). Note: batch 32 vs pi05-v4's 16 makes the A/B
# slightly less pure — accepted, we're optimizing for the best deployable model.
STEPS="${STEPS:-20000}"
SAVE="${SAVE:-1000}"
BATCH="${BATCH:-32}"
OUTDIR="${OUTDIR:-outputs/train/vial-sort-groot-v4}"
LOGFILE="${LOGFILE:-/tmp/groot_v4.log}"

.venv/bin/lerobot-train \
  --dataset.repo_id sari-abdan/vial-sort-v4-merged-ee \
  --dataset.root ./data/vial-sort-v4-merged-ee \
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

# NOTES:
# - base_model_path defaults to nvidia/GR00T-N1.5-3B inside the config; override with
#   --policy.base_model_path if needed.
# - GR00T pads state/action to max_state_dim=64 / max_action_dim=32 internally — our
#   7-dim EE features fit; do NOT pass pi05's max_*_dim overrides here.
# - If OOM at batch 16 (3B + diffusion head): halve batch_size, or set
#   --policy.lora_rank 32 for a LoRA run instead (GR00T's LoRA path is NVIDIA's own,
#   not the broken generic-PEFT path that sank our pi0 LoRA attempt).
# - Pick checkpoints by ROBOT eval, not loss (same rule as always).
