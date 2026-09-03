# BIN TOP-UP — fixing "carries to the bin but won't drop"

pi0.5-v5 (**12k**) does rack→rack sorts cleanly, but on "…to the bin" it carries the
vial over the bin and **hovers without opening the gripper**.

## Root cause: inconsistent demos, NOT a checkpoint
Rack placements were demonstrated **consistently** (lower into the slot, open). The bin
was demonstrated as varied **throws** — different height/angle/release-point each time.
Imitation learning **averages** demonstrations, so inconsistent throws collapse into a
hesitant "hover, don't commit." Confirmed: the bin fails at **8k, 12k, and 16k** — no
checkpoint fixes a data problem. (The bin is also the far-left **reach extreme**.)

So the fix is **data**, warm-started onto the working 12k model.

---

## THE FIX

### 1. [THOR] Record ~25–30 bin demos — the SAME drop every time
The pick may vary; the **drop must be identical**.
- **Source:** vary the pick slot across episodes (1, 3, 4, 6; both racks) so the *pick*
  generalizes.
- **Drop (identical every time):** carry to the **same spot over the bin CENTER** (not
  the side), lower ~2–3 cm, **open the gripper fully** — a *controlled release*, **not a
  throw**. Same motion, same spot, every episode.
- HOME before every episode. Same 4-camera setup as v5 (so it can merge).
- Record straight into **position-grammar** labels (skip relabel), one run per source:
```bash
# example: 5 eps, source = left rack slot 3 -> bin. Repeat for a few sources.
#   reuse the CAMS + COMMON env from record_v5.sh; just change num_episodes + single_task
lerobot-record $COMMON --robot.cameras="$CAMS" \
  --dataset.repo_id=sari-abdan/vial-sort-v5-binfix \
  --dataset.root=/home/robot/my_local_data_v5_binfix \
  --dataset.num_episodes=5 --dataset.episode_time_s=30 --dataset.reset_time_s=20 \
  --dataset.single_task="Move the vial from position 3 of the left rack to the bin." \
  --resume=true          # omit --resume on the FIRST run (it creates the dataset)
```
Do ~5 runs at different sources (e.g. L3, R1, L4, R6, L1) → ~25 eps, all clean drops.

### 2. [WS] Process + merge with the v5 set
```bash
# upload from Thor -> download on WS
huggingface-cli upload sari-abdan/vial-sort-v5-binfix /home/robot/my_local_data_v5_binfix --repo-type dataset
huggingface-cli download sari-abdan/vial-sort-v5-binfix --repo-type dataset --local-dir ./data/vial-sort-v5-binfix
# joint->EE, then drop cam_depth (RGB-only, to match vial-sort-v5-ee-rgb)
.venv/bin/python ee/convert_dataset.py --src ./data/vial-sort-v5-binfix --dst ./data/vial-sort-v5-binfix-ee --urdf ./SO101/so101_new_calib.urdf
.venv/bin/lerobot-edit-dataset --repo_id sari-abdan/vial-sort-v5-binfix --root ./data/vial-sort-v5-binfix-ee \
  --new_repo_id sari-abdan/vial-sort-v5-binfix-rgb --new_root ./data/vial-sort-v5-binfix-rgb \
  --operation.type remove_feature --operation.feature_names "['observation.images.cam_depth']"
# merge the bin-fix demos into the main RGB set (mind the stats 'count' fix if aggregating)
.venv/bin/lerobot-edit-dataset --new_repo_id sari-abdan/vial-sort-v5-ee-rgb-binfix \
  --new_root ./data/vial-sort-v5-ee-rgb-binfix --operation.type merge \
  --operation.repo_ids "['sari-abdan/vial-sort-v5-ee-rgb','sari-abdan/vial-sort-v5-binfix-rgb']"
```
Labels are already position-grammar, so **no relabel needed**. (If the ~25 bin eps feel
too thin vs 150, record 40 instead, or over-sample them at train time.)

### 3. [WS] Fine-tune FROM 12k (warm start — don't start over)
Point `pretrained_path` at the **12k checkpoint**, low LR, few steps, so it reinforces
the bin **without forgetting** the racks:
```bash
.venv/bin/lerobot-train \
  --dataset.repo_id sari-abdan/vial-sort-v5-ee-rgb-binfix \
  --dataset.root ./data/vial-sort-v5-ee-rgb-binfix \
  --dataset.image_transforms.enable true \
  --policy.type pi05 \
  --policy.pretrained_path outputs/train/vial-sort-pi05-v5/checkpoints/012000/pretrained_model \
  --policy.freeze_vision_encoder true --policy.train_expert_only true \
  --policy.dtype bfloat16 --policy.optimizer_lr 5e-5 \
  --policy.chunk_size 50 --policy.n_action_steps 50 \
  --policy.max_state_dim 32 --policy.max_action_dim 32 \
  --batch_size 16 --steps 8000 --save_freq 1000 --eval_freq 1000 --log_freq 100 \
  --output_dir outputs/train/vial-sort-pi05-v5-binfix
```

### 4. Deploy + test
Deploy an EARLY checkpoint (2k–6k of the fine-tune — warm-start converges fast), same as
12k (`--n-action-steps 15`, HOME_POSE already set), and test the bin **plus** re-check a
rack sort to confirm it didn't regress. Pick by robot, not loss.

---

## If it's still stubborn
- The bin is the reach extreme — double-check the arm can physically reach the bin center
  in home-relative space during the demos (don't demo drops it can't reproduce).
- Over-sample the bin demos in the mix, or record 40+ instead of 25.
- Keep the drop dead-consistent — that single factor is what turns "hover" into "release."
