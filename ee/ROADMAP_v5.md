# ROADMAP v5 — the whole process, in order (2026-07-08)

One checklist from "servo broken" to "v5 model deployed". Each phase has a **GATE** —
do not start the next phase until it passes. Detail lives in the linked docs; this file
is only the order and the gates.

**Depth audit result (2026-07-08): NO existing dataset has any depth** — all 9 local
datasets (v1→v4-merged, 794 eps) are 3-stream RGB; the only "depth" in their metadata is
the standard `"video.is_depth_map": false` flag. v5 is the first depth-carrying dataset;
nothing to salvage retroactively.

---

## P0 — Hardware back online  ← CURRENT BLOCKER
- [ ] Replace shoulder_lift ST3215 (id 2) — the one that burned (IK-seed runaway; those
      flags are permanently retired).
- [ ] Set the new servo's ID to 2 before installing (bus IDs must stay 1..6 in order).
- [ ] Recalibrate ONLY if the horn position changed: `so_follower` calibration
      (NEVER the divergent `my_follower_arm` one).
- [ ] 2-minute teleop smoke test.
- **GATE**: teleop smooth, no motor above warm-to-touch, zero "no status packet" errors.

## P1 — Rig freeze + camera anchor
- [ ] cam_top rigid mount + cable strain-relief FIRST (3 documented drifts; THE recurring
      root cause of placement regressions).
- [ ] Tape rack footprints + bin floor position (sheet layout rules).
- [ ] `ee/cam_align_live.py` / `ee/extract_ref_frame.py` vs `ee/align/reference_cam_*.png`.
- **GATE**: all 3 camera views overlay their v4 reference frames.

## P2 — Depth pre-flight (Thor) — optional lane, never a blocker
- [ ] USB check: D435i must report USB 3.x / 5000M (command in `ee/PLAN_FABLE.md` §1).
- [ ] Apply the 3-hunk `so_follower.py` patch BY HAND on Thor
      (`ee/DEPTH_PLAN.md` §"Thor patch" — colorize_depth + _cameras_ft + get_observation;
      stock lerobot records NO depth even with use_depth=true).
- [ ] 2-episode throwaway recording → must contain `videos/observation.images.cam_depth/`.
- [ ] 60 s 4-stream bandwidth bench → zero frame-drop warnings.
- **GATE**: both checks pass → record v5 WITH depth. Either fails → record WITHOUT
  (drop `"use_depth": true` from CAMS); the pilot proceeds regardless.

## P3 — Record the 200-episode pilot
- Sheet + CLI: `ee/initial_fable_v5.txt` (8 sessions × 25 eps; 4-stream CAMS JSON is in
  the sheet header). HOME before every episode. Sources only from anchor slots 1/3/4/6.
- [ ] After EVERY session (same day): `ee/audit_labels.py --root <dataset> --group`.
- **GATE per session**: audit clean AND total episode count advanced by exactly 25
  (resume appended — after session 2 the count must be 50, not 25).

## P4 — Post-process (WS)
- [ ] Upload from Thor → download to WS (`huggingface-cli`, same flow as v4).
- [ ] `ee/convert_dataset.py` joint→EE — remember the stats **'count' fix** (KeyError
      'count' in aggregate/merge; copy frame_index's count in; rm partial output first).
      cam_depth needs nothing special — it's a normal video key and rides along.
- [ ] `ee/paraphrase_tasks.py` on the converted set.
- **GATE**: features list shows state/action EE-7 + 3 (or 4) image keys incl. cam_depth,
  200 episodes, paraphrased labels spot-checked.

## P5 — Train (the 2×2: both models × ±depth, ONE dataset feeds all four)
NOTE: "RGB-only" needs NO filtering — cam_depth is just a dataset key you don't pass
in the train config. Same recorded data, four configs.
1. [ ] **pi0.5-v5 +depth** — primary candidate. Recipe = `ee/train_pi05_v4.sh` with v5
       paths + the cam_depth key.
2. [ ] **GR00T-v5 +depth** — hedge candidate. Recipe = `ee/train_groot_v4.sh`
       (BATCH=16, SDPA patch, vision unfrozen → best checkpoint EARLY, eval 3k-8k first)
       + the cam_depth key.
3. [ ] **pi0.5-v5 RGB-only** — the depth-value baseline (identical to run 1 minus the
       key). Without this the P6 "did depth help?" question is unanswerable.
4. [ ] **GR00T-v5 RGB-only** — optional completeness leg; run if time allows.
- If P2 failed (no depth recorded): collapse to runs 3+4 only — the plan degrades
  gracefully, nothing is blocked.
- **GATE**: checkpoints picked by ROBOT eval only — never by loss (v1 lesson: 30k lost
  to 6k/15k).

## P6 — Eval + decide
- Protocol: `ee/EVAL_TRIALS_groot_v4.md` generalized — 12-trial matrix per checkpoint
  (4 destinations × 3 sources), wrist-cam recordings, A–E grip scorecard.
- [ ] Robometer scores every recorded trial (`ee/assess_robometer.py --manifest ...`);
      ≥85% agreement with your eyeballing ⇒ adopt it as the standing judge.
- Decisions, in order:
  - [ ] pi0.5-v5 vs GR00T-v5 → winner becomes the deployed default, loser stays hedge.
  - [ ] +depth vs RGB-only → keep depth ONLY on a measurable first-try-grasp win.
  - [ ] Prune losing checkpoints (GR00T-v4 alone holds 214 GB in outputs/train/).
- **GATE (project)**: deployed model follows the prompt to all 3 pilot destinations and
  interpolates a held-out source slot (2 or 5).

## Parallel lane — anything here can run NOW, no hardware needed
- GR00T-v4 checkpoint ranking in sim: `bash isaac/eval_groot_v4.sh`
  (plumbing/language-geometry ranking only — unfrozen-vision domain gap means sim CANNOT
  score real grasp success).
- Robometer manifest prep + validation bookkeeping.
- Disk pruning of dead checkpoints/runs.

---
Detail docs: `ee/PLAN_FABLE.md` (rationale/§refs) · `ee/DEPTH_PLAN.md` (depth + Thor
patch) · `ee/initial_fable_v5.txt` (sheet + CLI) · `ee/EVAL_TRIALS_groot_v4.md` (trial
protocol) · `ee/Papers_v5.md` (reading list).
