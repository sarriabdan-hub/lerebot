# GR00T-v4 vs pi0.5-v4 — trial protocol (watch the trials, judge the GRIP)

Goal: pick the best deployable checkpoint AND see with your own eyes how each model
approaches, grips, and places — not just a success number.

## 0. Setup (once per checkpoint)
```bash
# WS -> Thor (or use isaac/vla_sim_server.py while the servo is out):
rsync -a outputs/train/vial-sort-groot-v4/checkpoints/<STEP>/pretrained_model/ \
      robot@192.168.123.198:/home/robot/dev/lerebot/ckpt_groot_v4_<STEP>/

# Thor — note the TWO video recorders: one run gets the WRIST cam (the grip
# close-up you asked for), rerun the same scenario with cam_side for the overview.
conda run -n lerobot --no-capture-output \
  python /home/robot/dev/lerebot/ee/vla_server.py \
  --checkpoint /home/robot/dev/lerebot/ckpt_groot_v4_<STEP> \
  --n-action-steps 16 --async-chunks \
  --filter oneeuro --euro-min-cutoff 0.3 --euro-beta 0.02 \
  --record-video --record-cam cam_wrist \
  --log-file /tmp/vla_runs.jsonl 2>&1 | tee /tmp/vla_server.log
```
- GR00T checkpoints: `--n-action-steps 16` (its native regime). pi05 checkpoints: 15.
- `--record-video --record-cam cam_wrist` = full-res grip close-up per execute ->
  `ee/presentation/exec_cam_wrist_*.mp4`. Use `cam_side` for placement overview runs.
- Safety watchdog is on by default; home before every trial (policy).

## 1. Which checkpoints to watch
Unfrozen-vision run -> evaluate EARLY first: **3k, 5k, 7k, 10k**, then 15k/20k only
if 10k still improves. (Frozen pi05-v4 reference: its 16k.)

## 2. The trial matrix (per checkpoint — 12 trials, ~15 min)
| # | Prompt | Source slot | What to watch |
|---|--------|-------------|----------------|
| 1-3 | "…position 1 of the left rack."  | R1, R4, R6 | approach line, grip centering |
| 4-6 | "…position 6 of the left rack."  | R1, R3, R6 | far-slot reach, drop-in angle |
| 7-9 | "…position 6 of the right rack." | L1, L4, L6 | direction switch follows prompt? |
| 10-12 | "…position 3 of the left rack." | R3, R4, R1 | mid-slot precision |
Same matrix for every checkpoint and both models — comparability is the point.

## 3. GRIP scorecard (fill one row per trial while watching / from wrist video)
For each trial note 0/1 for each column:
  A approach: moves straight to the correct vial, no hunting
  B first-try grip: closes ON the vial body, centered, no re-grab
  C carry: no slip/tilt during transport
  D placement: enters the prompted slot, no rack collision
  E prompt: went to the PROMPTED destination (the language test)
Success = all of A-E. Log rows in ee/eval_results.csv via the UI buttons, or a sheet.

## 4. Auto-scoring the recorded videos (after each session)
```bash
scp "robot@192.168.123.198:/home/robot/dev/lerebot/ee/presentation/exec_*.mp4" ee/presentation/
ee/robometer/.venv/bin/python ee/assess_robometer.py --manifest ee/robometer_pilot.csv
```
(Manifest rows: video,task,ground_truth from your scorecard — this doubles as the
Robometer validation pilot: agreement >=85% = adopt it as the judge.)

## 5. Reading the result
- E-column rate = the language-following A/B (the reason this run exists).
- B-column rate = grip quality (what you want to see) — compare wrist videos of the
  best GR00T vs best pi05 checkpoint side by side.
- jitter_deg + infer_lat from /tmp/vla_runs.jsonl = smoothness/latency comparison.
- Decision per PLAN_FABLE §7: better model becomes the v5 training default; loser
  stays the hedge.
