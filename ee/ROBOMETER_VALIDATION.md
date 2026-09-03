# Robometer Phase-0 validation — findings (2026-08-19)

Goal of Phase 0: does the Robometer-4B "referee" detect OUR vial failures well enough to build on?
Tooling: `ee/assess_robometer.py` (fixed: torchao removed, bf16 cast, force standard loader, read
**peak** success not last-frame) + `ee/extract_episode_clips.py` (per-episode clips from the v3 dataset).
All scoring at **fps=3** (fps=1 starves short clips → false zeros; this cost us several runs to find).

## 1. The machinery is valid ✅
On Robometer's own example clips at fps=3 we reproduce the published reference outputs almost exactly:
soar **0.879** (ref 0.879), berkeley **0.973** (ref 0.973), jaco 0.598 (ref 0.523). The model loads
and runs correctly; the earlier "everything scores 0" was an fps bug, not a broken model.

## 2. Progress head works on our domain ✅
On 15 real successful demos, progress rises to ~0.75–0.87 during every manipulation. Usable signal.

## 3. Success head, zero-shot: PARTIAL ⚠️
Read at the **placement peak** (not the last frame — full episodes end with the arm retreating home,
which drops both progress and success), **9/15** real successes score success ≥0.5 (mean 0.53).
`success@progpeak ≈ success_max`, i.e. success fires at the moment of placement. So the referee
half-recognizes our successes — better than it first looked, but 40% false-negatives.

## 4. Fine slot-level discrimination, zero-shot: NO ✗  (this is the user's #1 need)
Same real-success video, scored against the correct destination vs a wrong one (success_max):

| clip | correct | wrong | gap |
|---|---|---|---|
| ep60 slot1-left vs slot6-left | 0.645 | 0.124 | **0.52 (strong)** |
| ep0 bin vs a rack slot | 0.691 | 0.404 | 0.29 (moderate) |
| ep10 slot1 vs slot6 (right) | 0.562 | 0.480 | 0.08 |
| ep30 slot3 vs slot6 (right) | 0.586 | 0.555 | 0.03 |
| **ep30 slot3 vs slot4 (right)** | 0.586 | **0.516** | **0.07 ← the 3→4 case** |
| ep40 slot6 vs slot1 (right) | 0.832 | 0.809 | 0.02 |
| ep70 hole3 vs hole6 (right) | 0.836 | 0.816 | 0.02 |

The referee catches gross differences sometimes (bin-vs-rack; one far left-rack pair) but **cannot tell
which slot within a rack** the vial went to. The exact **3→4** confusion the user wants to catch shows a
gap of **0.07 — noise.** Zero-shot Robometer is not a slot-precise judge.

## Verdict
- **Good for:** holistic progress, a crude success/fail signal, and (untested but plausible) **gross**
  failures like a vial dropped on the table or never grasped — a bigger visual change than 3-vs-4.
- **Not good for (zero-shot):** which-slot precision (3→4), subtle misplacement/rotation quality.
- **Key implication:** the user already has a **classical CV slot-reader** (`ee/slot_reader.py`,
  used in `ee/cv_run.py`) that detects which vial sits in which slot. For 3→4 and drop-in-front, that
  deterministic, slot-geometry-aware check is the *right* tool; Robometer is better as a general
  progress/quality signal, not a slot judge.

## Options from here
- **A — Split by strength (recommended):** slot-reader verifies placement (3→4, drop-in-front);
  Robometer supplies holistic progress/success for the scoreboard + gross-failure retry. Confirm on a
  few real drop clips.
- **B — LoRA-adapt Robometer** on our own success/failure clips to teach fine slot discrimination.
  Higher effort, needs recorded failures, uncertain payoff on the hardest (adjacent-slot) case.
- **C — Robometer only for gross signals** (progress + no-grasp/drop), leave 3→4 to the slot-reader
  entirely.

All three need the same missing ingredient next: a short **Thor session recording real policy failures**
(rotated-drop, 3→4, edge 1/6) with `--record-video`, to (a) confirm gross-failure detection and (b) be
the LoRA/labeled set if we go path B.

## Reusable artifacts produced
`ee/extract_episode_clips.py`, `ee/robometer_scoreboard.py`, `ee/ROBOMETER_SETUP_NOTES.md`,
`ee/demo_manifest.csv` + `ee/episode_clips/` (15 scored demos), `ee/demo_scores.jsonl`.
