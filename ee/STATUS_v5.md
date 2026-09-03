# STATUS_v5 — vial-sort v5 handoff (2026-08-07)

Single source of truth for where the v5 effort stands, the frozen conventions, the
commands, and every gotcha we hit. Read before making a change.

## WHERE WE ARE — v5 TRAINED + DEPLOYED (results 2026-08-12)
- **150 episodes recorded**, relabeled to POSITION grammar (source->dest), RGB-only.
  Trained pi0.5 (frozen, expert-only, 30k) + GR00T-N1.5 (frozen, 20k) on the SAME data.
- **BEST CHECKPOINT: pi0.5 12k**  (`outputs/train/vial-sort-pi05-v5/checkpoints/012000`).
  Deploy: `--n-action-steps 15`, HOME_POSE set to the v5 start pose (in vla_server.py).
  - WORKS: follows the language prompt every time; grasps slot 3; **rack->rack sort
    completes — lowers into the slot AND releases.** A real autonomous vial-sort. ✅
  - WEAK: **bin** — carries over but won't drop (inconsistent-throw DATA, not a checkpoint;
    fix = `ee/bin_topup.md`). Edge slots **1 & 6** hard to grasp (reach extreme).
  - Checkpoint curve: **8k** = doesn't follow the prompt (undertrained); **12k** = sweet
    spot; **16k** = overfit (lost the grasp); higher = worse. Deploy **12k**.
- **NEXT — reliability comes from MORE DATA.** 150 eps buys a working demo, not high
  success (~50-70% on trained combos). To make ALL tasks reliable (incl. bin + edge
  slots 1/6), **RECORD MORE toward 300 -> 1000** (denser per source/dest) and retrain
  with the same recipe. First targeted add = the bin top-up (`ee/bin_topup.md`).

## TASK & ARCHITECTURE
SO-101 arm + Jetson Thor. Sort colored vials into rack slots / bin by language.
A VLM plans the sort (mismatch -> trash) and issues atomic commands; the VLA (pi0.5)
executes one skill: "put the {color} vial in {destination}", color-grounded in clutter.

## RECORDING SETUP & CONVENTIONS  (FROZEN — do not move racks/cameras)
- **3 colors:** R=red, C=cyan, G=dark green. Exactly 3 physical vials of each.
- Two 6-slot racks arranged DIAGONALLY to the arm; BIN/trash beside them on the LEFT.
- **Perspective = the SIDE camera** (front RealSense), NOT your body:
  LEFT rack = image-left (the one by the bin); slots 1->6 = left-to-right in the side image.
- Scene rules: every vial SPACED (no two adjacent, so pick+drop have finger room),
  <=3 vials/rack, distractors never the target colour, never >3 of any colour (you have 3).
- **Depth:** cam_side use_depth=true -> a colorized `cam_depth` stream is recorded on
  EVERY episode. You CANNOT mix depth/no-depth in one dataset (schema locks at ep 0).
- 4 camera streams: cam_top, cam_wrist, cam_side (RealSense colour), cam_depth.

## SCRIPTS (Thor: /home/robot/dev/lerebot/ee/)
- `SORT_SHEET_v5.md`     — the 300-ep sheet (60 runs x 5). Read by the record scripts.
- `gen_sort_sheet.py`    — regenerates the sheet. To change size/colours: edit the top
  constants (N_RUNS, COLORS, ...) and rerun `python ee/gen_sort_sheet.py`.
- `record_v5.sh N`       — record run N (5 eps). Auto-resumes/appends by episode count.
- `record_v5_session.sh A B` — chains runs A..B, showing each prompt + scene, ENTER between.
- Prefix `DISPLAY_DATA=true` on either to turn the rerun viewer ON (costs some framerate).

## KEY COMMANDS
```
# continue recording (NO rm when appending!):
DISPLAY_DATA=true bash ee/record_v5.sh 13            # or: record_v5_session.sh 13 30
# true episode count (files != episodes; they are chunked):
python3 -c "import json;print(json.load(open('/home/robot/my_local_data_v5/meta/info.json'))['total_episodes'])"
# motor-bus sanity (must show {1..6}):
python -c "from lerobot.motors.feetech import FeetechMotorsBus;print(FeetechMotorsBus.scan_port('/dev/ttyACM0'))"
# view an episode (all cams+state) in the laptop browser:
lerobot-dataset-viz --repo-id sari-abdan/vial-sort-v5-pilot --root /home/robot/my_local_data_v5 \
    --episode-index N --mode distant --web-port 9090     # open http://192.168.123.198:9090
```

## GOTCHAS WE HIT (all real, all cost time)
- **Motor bus "no status packet" / "missing motor N"** wandering across IDs = a MARGINAL
  CABLE, not a burned motor (a scan still shows all 6). Reseat the chain + power; get
  3 clean scans before recording. Never record through a flaky bus (corrupts data).
- **Depth + record connect timing:** enabling depth at record-connect can trip the motor
  write; `warmup_s: 8` in the CAMS (already set in record_v5.sh) gives it time to settle.
- **Flaky keyboard spams the `->` key** -> starts+exits an empty episode -> crash
  ("must add frames before add_episode"). Ctrl+C the instant `->` repeats; use a solid
  keyboard; record run-by-run so one bad key event costs at most one run.
- **`lerobot-edit-dataset` does NOT edit in place** — it writes the result to
  `~/.cache/huggingface/lerobot/<repo_id>/`, leaving your `--root` untouched. To apply:
  `rm -rf <root>` then `mv ~/.cache/.../<repo_id> <root>`.
- **No `rm` when appending** — `rm` only to restart run 1 from scratch. Appending is the
  default from run 2 on; deleting wipes prior episodes.
- **Bad episode:** note the index, delete them ALL at the END before training (deleting
  mid-recording re-indexes and breaks the resume-count check).
- Distractor colour/placement can drift from the sheet — only the TARGET colour and the
  DESTINATION must match (they are the label). Distractors just need to be non-target and spaced.

## AFTER RECORDING (WS pipeline)
```
[THOR] huggingface-cli upload sari-abdan/vial-sort-v5-pilot /home/robot/my_local_data_v5 --repo-type dataset
[WS]   huggingface-cli download sari-abdan/vial-sort-v5-pilot --repo-type dataset --local-dir ./data/vial-sort-v5-pilot
[WS]   ee/convert_dataset.py  (joint->EE; remember the stats 'count' fix; cam_depth rides along)
[WS]   ee/paraphrase_tasks.py (UPGRADED for 3 colours + bin) -- run ONCE on the EE dataset
[WS]   train pi0.5 (train_pi05_v4.sh recipe + v5 paths + depth)  -- ask for the exact command at 150
```

## MODEL STRATEGY
pi0.5 primary; A/B with **SmolVLA** + **GR00T+LoRA** on the same v5 data (2x RTX6000).
World-Action Models (LingBot-VA/Cosmos) are OUT: 5.2s/inference, sim-only. Full doc:
`ee/MODEL_STRATEGY_v5.md`. A3/B6 UI codes -> decouple: UI shows a code, dataset stores
the natural-language label.

## PATHS & IDs
- WS 192.168.123.170 (user sari) · Thor 192.168.123.198 (user robot)
- Dataset root: /home/robot/my_local_data_v5 · repo_id: sari-abdan/vial-sort-v5-pilot
- Other docs: ee/ROADMAP_v5.md · ee/MODEL_STRATEGY_v5.md · ee/DEPTH_PLAN.md ·
  ee/MILESTONES.txt · ee/Papers_v5.md · ee/align/new_rack_side.png (setup reference)
