# PLAN_FABLE — vial-sort v5: answers, code, and the road map
*(written 2026-07-05, after the shoulder_lift burnout. Arm is DOWN until the ST3215 is replaced.)*
*Reading list with per-paper focus notes → **`ee/Papers_v5.md`** (all links verified).*
***Execution order (phases + gates, servo→deploy) → `ee/ROADMAP_v5.md`** (2026-07-08).*

---

## 0. What just got built (code, ready now)

**Motor safety watchdog — `ee/vla_server.py`** (the thing that would have saved the servo):
- During every execute (sync, async, AND rtc paths), the control loop reads
  `Present_Temperature` + `Present_Current` from all 6 motors every ~10 steps (~0.5 s).
- Trips on: any motor ≥ **55 °C** (sts3215 self-protection is ~65 °C, we act first), or
  sustained stall current ≥ **1400 mA for 3 consecutive checks** (one spike = normal
  acceleration; sustained = arm pushing against an obstacle, winding cooking).
- On trip: **stops the run + torque-disables the whole bus** (arm goes limp — a sag beats
  a fire), prints `*** SAFETY TRIP ***`, sets UI phase to `error`.
- Flags: `--safety-temp-c 55 --safety-current-ma 1400 --safety-strikes 3
  --safety-interval-steps 10`, kill switch `--no-safety` (don't).
- **Calibrate after the servo swap:** run one normal placement, watch the printed trip
  values; if a healthy motion trips (false positive), raise `--safety-current-ma` to just
  above the observed peak. Deploy = scp `vla_server.py` to Thor (do NOT scp
  `rollout_pi0_lora.py` — Thor's copy has the camera fix).

**Motor telemetry → Grafana (BUILT):** the watchdog now writes one JSON line per check
(temps °C + currents mA, all 6 motors) to `--telemetry-file /tmp/motor_telemetry.jsonl`
(default ON). **`ee/telegraf_motor.conf`** tails it → InfluxDB → Grafana; full setup steps
are in that file's header (docker one-liners for Influx+Grafana, token, dashboard query,
and a 50 °C/1200 mA Grafana alert that warns BEFORE the 55 °C/1400 mA watchdog trip).
No MQTT broker — single consumer, Telegraf tail is simpler; revisit if the orchestrator
also wants the stream.

**Label audit (BUILT + RUN):** `ee/audit_labels.py --root <dataset> [--group]` lists every
episode's task + per-task totals. Result for v4-merged (2026-07-05): **labels are clean** —
blocks match TRAINING_COVERAGE_v4.txt exactly (33 left1 / 20 left3 / 33 left6 / 32 right6,
118 eps). The remembered sheet-deviation is not visible at destination level; if it was a
SOURCE-slot deviation it's unrecorded (sources aren't in metadata) and harmless for training.

### REFINEMENTS (2026-07-05, post paper Q&A — supersede where they conflict)
- **Adaptive episode budget:** 600 (50/dest) → train → per-destination eval → TOP UP only
  weak destinations (+25-50 each). Paper 3's tasks were simpler than slot-insertion, so its
  curve is optimistic — but our 12 destinations share grasp/transport structure, so blind
  1200 is waste; adaptive top-up converges cheaper.
- **"Sort all the vials by color"** = orchestrator's job, not the policy's: the planner
  (cv_run) decomposes into single-placement prompts → /execute per vial. No long-horizon
  episodes needed. (Base pi0.5 could learn it, but only from full-sorting demos.)
- **Hedge model = pi0_fast, not pi0:** LIBERO-Plus, camera-viewpoint perturbation:
  pi0 94.2→15.8% vs pi0-fast 85.5→66.4%. If v5 still hurts on camera shifts, A/B pi0_fast
  (in lerobot) on the same data before anything exotic.
- **Home-every-episode is now POLICY** (recording + eval): robot-initial-state is the other
  top VLA fragility (95→<30%); homing removes it. Already our habit — keep it.
- **FTM pilot (cheap, high upside):** Feature Token Modulation = ~4K-param affine on visual
  tokens, adapts from ONE demo in ~750 steps (arXiv 2512.02902). If ported to our pi05 stack
  it replaces the 20-30-ep camera re-anchor protocol with a minutes-long repair. Pilot AFTER
  v5 ships; re-anchor protocol stays the fallback. Augmentation stays ON regardless
  (proactive defense; FTM is reactive repair — complementary, not either/or).
- **Not doing:** EWC (we have replay data; low vision-LR + val early-stop suffice), LIBERO
  (sim-only Franka — can't run our SO-101 checkpoint), Plücker camera conditioning
  (architecture fork; RealSense depth/IMU ≠ the required extrinsics).
- **Terminology anchor:** our pi0.5 is supervised fine-tuning (hundreds of demos,
  in-distribution) — not zero-shot / one-shot anything.

### DECISIONS (2026-07-05)
- **600 episodes (50/dest), fixed camera pose for ALL of it.** Multi-POV deferred.
- Old v4 episodes are reused IF the camera alignment check passes vs the reference frame;
  a printed floor/tape restore mark + `cam_align_live` = the "restore the old pose" tool.
- Sessions of **~25 eps**: each session = 5 destinations × 5 eps, rotating; across sessions
  make sure every destination appears under ≥3 different lighting/day contexts.
- **Other employees will record** → they follow `ee/RECORDING_SHEET` protocol; every session
  ends with `audit_labels.py --group` to catch label mistakes same-day, not at merge time.
- Unfrozen-vision variant WILL be trained (97 GB RTX 6000 = ample; see §7 glossary).

---

## 1. Depth — why we're not using it (and the command to check your port)

> **2026-07-08 UPDATE — full depth verdict now in `ee/DEPTH_PLAN.md`**: "Lingbot" is a
> name collision (lerobot's LingBot-VA = RGB-only world model, unusable on Thor; the
> depth-aware LingBot-VLA isn't in lerobot and doesn't take live depth either). The viable
> path is recording D435i depth as a COLORIZED 4th camera (`cam_depth`) during the v5
> pilot and A/B-ing pi0.5/GR00T with/without it — see that doc for the recipe + decision rule.

Two independent reasons, and the USB port is not one of them:

1. **The policy can't eat depth natively.** pi0/pi0.5 are RGB-only VLAs — PaliGemma's vision
   tower takes 3-channel images. `use_depth=False` in our config; there is no depth input in
   the training data or the model. (The `cam_depth` colorized-stream trick in DEPTH_PLAN.md
   is the exception — it feeds depth AS an RGB image, no architecture change.)
2. **Where depth WOULD help** is the *assessment layer* (§4): verifying the vial actually
   descended into a slot (insertion depth), tabletop height sanity. That's a later add-on
   to the verifier, not the policy.

**Check which USB the RealSense is really on (run on Thor):**
```bash
python -c "
import pyrealsense2 as rs
for d in rs.context().query_devices():
    print(d.get_info(rs.camera_info.name), '-> USB', d.get_info(rs.camera_info.usb_type_descriptor))
"
# and the kernel view:  lsusb -t   (find the 8086:0b3a device: 480M = USB2, 5000M = USB3)
```
Note: on 2026-07-01 `lsusb -t` showed it at **480M on Bus 001 (USB-2)** — that was the root
of the camera-starvation saga. If you've since moved it to a blue port, the command above
will show `USB 3.x` and we get bandwidth headroom back (then depth for the verifier becomes
cheap too). Show me the output and I'll confirm.

## 2. Old episodes + camera placement — can v5 reuse them?

**Yes, reuse them — IF the cameras haven't moved since v4 was recorded.** The frozen-vision
lesson: the policy memorizes pixel-level context, so episodes recorded at a different camera
pose actively *hurt* (that's what killed base_v1 after the bump). Protocol:

1. Before any new recording, run the alignment check against the stored reference frame
   (`cam_align_live` / `extract_ref_frame` workflow) for ALL THREE cameras.
2. **Aligned** → v5 = v4-merged (118 eps) **+ new episodes**, merged with `merge_v4.py`
   pattern (remember the stats `count` fix — inject `frame_index`'s count).
3. **Moved and can't be re-aligned** → old episodes are dead weight for placement precision;
   record fresh and treat v4 as pretraining data at most.
4. FIRST: fix the top-cam mount mechanically (strain-relief / lock) — it has drifted 3×
   and each drift invalidates data. Rigid mounts are what make "reuse old episodes" possible.

**New recordings, same camera placement?** Yes — identical placement to the (aligned)
current pose. Camera *diversity* is NOT the goal for v5 (that multiplies data needs, §6);
rack-position diversity is.

## 3-pre. TASK SPEC v5 (updated 2026-07-05 — supersedes "red vial only")

- **Vials: up to 4 colors** (e.g. red/blue/green/yellow), **max 4 vials per rack** — this is
  a SCENE-START rule: each episode begins with 1-4 vials scattered in random slot patterns
  (e.g. 1,3,4,5 / 2,5,6 / just 3), mixed colors. Occupancy is a RANDOMIZATION axis, not an
  enumeration — never a combinatorial coverage requirement. All 6 slots stay valid
  destinations (13 dests with bin). Per-session dice: ~40% 4-vial / 30% 3 / 20% 2 / 10% 1.
- **Prompts become color-conditioned**: "Place the BLUE vial in position 2 of the left rack."
  The policy must SELECT the right vial among other-color distractors — a new visual-grounding
  dimension on top of destination-following.
- **New destination: the BIN** (side). New motion primitive too — a release-over-bin drop is
  a different endgame than a slot insertion. Bin at a FIXED position for the pilot; vary its
  position slightly in full v5 (like the racks).
- **"Sort by color count" logic lives in the ORCHESTRATOR**, not the policy: the planner
  looks at the scene (later: LocateAnything), decides which vial goes where (or to the bin),
  and emits single color+destination prompts. The policy only ever executes one placement.
- **Compositionality rule (critical):** colors × destinations must be CROSSED in the data.
  Never let a color correlate with a destination (e.g. all blue → bin), or the model fuses
  them and won't follow novel combinations. Every color must appear going to every
  destination group, with 1-3 other-color vials in scene as distractors.
- ~~OPEN QUESTION~~ RESOLVED: "max 4/rack" = scene-start rule (above); prompts may name any
  slot → destination set = 12 slots + bin = **13**.
- **FINAL BUDGET: ~700-800 eps** = pilot ~200 (2 slots+bin) + Phase B ~500 (remaining 10
  dests × ~50, rack/bin shifts) + adaptive top-up 0-100. Coverage targets: ≥50 eps per
  DESTINATION and ≥50 per TARGET-COLOR; scene patterns randomized inside those, never
  enumerated.

## 3a-pilot. PHASE A — pilot dataset (~200 eps) BEFORE the full v5

Goal: validate the TWO new hard things (color grounding, bin drops) + the pipeline, cheaply,
before the 600-ep commitment. Same camera pose as v4 (aligned); racks FIXED in place for the
whole pilot (full v5 adds rack shifts later; merging fixed-rack pilot + shifted-rack v5 data
is fine — the pilot just contributes the "canonical position" slice of the diversity).

| Pilot element | Choice |
|---|---|
| Destinations | 2 rack slots (suggest LEFT 1 + RIGHT 3 — one per rack, different depths) + BIN = 3 |
| Colors | ALL 4 from day one (color is the thing under test) |
| Episodes | ~200: ≈65/destination; ≈50/color, interleaved, colors×dests crossed |
| Scene | 2-4 vials per episode, mixed colors, prompt names exactly one |
| Sources | anchor slots 1,3,4,6 as before, either rack |
| Sessions | 25-ep sessions, destination rotated every ~5, home every episode |
| Labels | paraphrased, color-conditioned |

Train on pilot alone (warm-start pi05) → eval: does it pick the RIGHT color ≥90%? Does the
bin drop work? Prompt-follow between the 2 slots? → fix whatever's broken (this is where
recording-protocol bugs surface at 200-ep cost, not 600) → then Phase B records the remaining
destinations and rack-shift diversity, and v5 = merge(pilot, phase B).

## 3. v5 recording — scenarios, diversity, and episode budget

**The v4 flaw ("session bundling"):** 20 same-destination episodes recorded in one block share
lighting/time/setup, so the model can shortcut "visual context → destination" instead of
"prompt → destination". **Interleaved** = the fix: rotate the destination every ~5 episodes
(`ABCDBACD…`, short CLI runs with `--resume=true`) so nothing except the PROMPT predicts
the destination.

### Episode budget (tiers — pick by available time)
| Tier | Eps/dest | Total (12 dests) | Expectation (SO-101 curve) |
|------|----------|------------------|----------------------------|
| Floor | 30 | ~360 | placements work, some misses |
| Target | 50 | ~600 | ~"48→70%" band, clearly better |
| +Multi-POV (§3b) | ×2 | 720–1200 | adds camera-move robustness |
Curve reference: 20 eps≈18%, 50≈48%, 100≈70%, 200≈75% per task (arXiv 2512.11921) —
returns diminish past ~100/task; source-slot variety inside each dest counts toward it.

### The DIVERSITY CHECKLIST (every recording session)
- **Destination**: rotate every ~5 eps across all 12 (both racks, pos 1–6). Interleave days too.
- **Source slot**: cycle anchors 1,3,4,6 every episode (2,5 stay held-out for interp testing).
- **Rack positions**: shift both racks 2–5 cm (and slight rotation) every ~10 episodes.
  This is what teaches relative geometry instead of pixel targets.
- **Lighting**: vary between blocks (lamp on/off, blinds, time of day).
- **Clutter/distractors**: blue vial + random objects in ~30% of episodes, positions varied.
- **Start pose**: home pose ± small jitter on a few episodes.
- **Labels**: paraphrased (`paraphrase_tasks.py`) — never one fixed template.
- **What stays FIXED**: camera placements (unless doing §3b deliberately), calibration,
  the physical racks/vials themselves.
Then: joint→EE convert → merge (+stats-count fix) → train.

### 3b. Multi-POV option — making camera moves survivable
Why the wrist cam already tolerates motion: its pose is derivable from joint state
(proprioception tells the model where it is) and its motion is in the training data.
Humanoids' cameras work the same way — the motion is trained, not surprise. Our failure mode
is a STATIC cam that moves BETWEEN train and test with no signal. To buy POV robustness:
record the same interleaved plan from **3–4 distinct tripod positions for top/side cams**
(e.g. per day: day1 pose A, day2 pose B, …; episodes evenly split). Cost: multiplies episodes
(hence the ×2 tier). Payoff: moving a camera later degrades gracefully instead of breaking.
Decision: do the Floor/Target tier FIRST at fixed poses; add POV tiers only after §8 eval
proves the base task. (True any-viewpoint invariance = camera-pose-conditioned policies,
arXiv 2510.02268 — out of scope.)

## 4b. Robometer — candidate to REPLACE LocateAnything as the success judge
[arXiv 2603.02115](https://arxiv.org/abs/2603.02115) (RSS 2026) — general-purpose reward model:
8 video frames + instruction → per-frame progress + explicit success/fail, zero-shot.
Qwen3-VL-4B base; SO-101 appears in their OOD eval; real-robot RL result: π0 20%→85% (DSRL)
with Robometer as the automatic success detector; failure detection (stall/drop) F1 0.81.
**DO NOW (works while the arm is down):** validation pilot on the WS — run it over ~30 of our
already-recorded videos with KNOWN outcomes (v4 episodes = successes; eval exec_*.mp4 = mixed)
and measure agreement. ≥85% → Robometer becomes ee/assess.py's success judge + the phase-3 RL
reward; LocateAnything drops to scene-state duty for the orchestrator (which slots occupied).
Also enables a TASK-level watchdog later (abort on progress stall) next to the motor watchdog.
Check code/weights license before productizing (same as LocateAnything).

## 4. LocateAnything as the assessor — yes, adopt it

[nvidia/LocateAnything-3B](https://huggingface.co/nvidia/LocateAnything-3B): open-vocabulary
text→boxes grounding, 3B (fits Thor alongside pi05). It is a *perception* model, not a policy.
Three jobs here:
1. **Auto-scoring evals** — after each execute, feed it the side-cam frame + "red vial in
   the left rack" style queries; box position vs. known slot geometry = success/slot-error.
   Replaces manual outcome buttons; writes `eval_results.csv` automatically.
2. **The reward signal for §5** (self-improvement needs exactly this success detector).
3. **Auto-labeling** recordings (which slot the vial started in — metadata we currently lose).
Build order: standalone `ee/assess.py` (frame → verdict) first, wire into the server's
post-execute hook after it proves reliable on ~20 hand-checked frames.

## 5. Early stopping — yes, done properly (val split)

Clarification: "the 30k checkpoint was worst" referred to OUR v2 run specifically — its
30k-step checkpoint had the lowest TRAIN loss yet placed worse than its 12k/15k checkpoints.
That's the classic reason train-loss-only stopping misleads on imitation learning; the
general early-stopping idea (train long, stop when a HELD-OUT metric degrades) is correct
and v5 will use it. The versions, cheapest first:
1. **Checkpoint often + pick by real-robot eval** (current practice — keep `SAVE_FREQ=2000`).
2. **Held-out validation loss** — hold out ~10% of episodes (stratified: one episode per
   destination), compute val loss per checkpoint offline, stop when val loss rises while
   train loss falls. This IS principled early stopping and catches gross overfit for free.
   → build `ee/val_loss.py` (loads checkpoints, runs forward pass on held-out eps).
3. **LocateAnything-scored eval sweep** (once §4 exists): auto-run N placements per
   checkpoint, pick by success rate. The real metric, automated.

## 6. Autonomous self-training (reward/penalty) — possible, with eyes open

What you're describing is **real-world RL fine-tuning**, and LeRobot ships an implementation:
**HIL-SERL** (human-in-the-loop sample-efficient RL) — see the LeRobot `hilserl` docs/examples.
The honest breakdown for our setup:
- **Reward**: solvable — LocateAnything verdict (§4) = +1/0 per episode. ✔
- **Safety**: solvable — the new watchdog + EE bounds. ✔ (mandatory for unattended runs)
- **The hard part — RESET**: after each attempt the vial must return to a start slot.
  A failed grasp leaves it anywhere (or on the floor). Options: (a) human babysits resets
  (that's the "HIL" — realistic), (b) scripted reset motion when the vial lands in a known
  region + LocateAnything localizes it (partial autonomy), (c) accept only self-resetting
  variants (move vial rack→rack forever, alternating direction — actually a decent fit!).
- **Verdict**: NOT the v5 path (imitation on 360 diverse eps is the proven, cheaper win),
  but a strong **phase 3**: warm-start from the v5 policy, alternate-direction task for
  self-resetting, LocateAnything reward, watchdog armed, you nearby. Worth doing after v5.

## 7. pi0 vs pi0.5 / model choice (from the review — decided)

Stay on **pi0.5** (open-world generalization matches the rack/camera goals; the port now
works with transformers 5.5.4).

**HEDGE #1 = GR00T N1.5 (assessed 2026-07-06):** NVIDIA's VLA has *first-class* SO-101 +
Jetson Thor support (official fine-tune-and-deploy guides for exactly our hardware) and is
already a LeRobot policy in our tree (`policy.type=groot`). Third-party benchmark (VILAS,
arXiv 2605.02037): pi0.5 wins **language-conditioned** tasks decisively (0.67 vs 0.40 avg
success) — and prompt-controlled destinations are OUR core axis, hence pi0.5 stays primary.
But GR00T wins **sequential multi-grasp consistency** (58% vs 36%; single-grasp tie 82/84)
and its 16-step chunks re-observe more often natively. TRIGGER to run the hedge: v5 pi0.5
underperforms on prompt-following or Thor latency → train GR00T on the SAME v5 dataset
(one run) and A/B on the robot. pi0_fast remains the camera-robustness hedge specifically.
Add to the train script: `--policy.compile_model=true --policy.gradient_checkpointing=true
--policy.dtype=bfloat16`. Try one **unfrozen-vision** variant (with 300+ eps it's viable and
it's the real cure for pixel-memorization).

*Glossary — "unfreeze the vision encoder":* frozen = the image-understanding layers keep
Physical Intelligence's original weights and only the action expert trains (cheap, but the
policy memorizes pixel→motor mappings — why the camera bump broke base_v1). Unfrozen = the
vision layers also update on OUR scenes (racks/vials/lighting) — better adaptation, needs
more data/VRAM/lower LR to avoid forgetting general vision.

## 8. Racks & cameras moving — the adaptation ladder

- **Rack positions: solved by v5 data** (racks shifted between blocks → policy learns
  relative geometry, not pixel targets).
- **Small camera drift: solved by augmentation** (`image_transforms` ±5° affine, ON).
- **Deliberate camera relocation: re-anchor protocol** — 20–30 fresh episodes at the new
  pose + warm-start finetune (~12k steps). Documented cost, not a crisis.
- **True viewpoint invariance**: research-grade (camera-conditioned policies / Plücker
  embeddings — arXiv 2510.02268); not our fight this quarter.

---

## THE ORDER OF OPERATIONS

| # | What | Gate |
|---|------|------|
| 1 | Replace shoulder_lift ST3215 (check label/BOM for exact variant) | part arrives |
| 2 | Bus verify: `scan_port` + 100-read + temps; calibrate watchdog thresholds | all pass |
| 3 | Camera alignment check vs reference frames; lock top-cam mount | aligned |
| 4 | Decide old-episode reuse (per §2) | step 3 |
| 5 | **PHASE A pilot** (§3a-pilot): ~200 eps, 2 slots + bin, 4 colors crossed, racks fixed | — |
| 6 | Train on pilot (warm-start pi05) → eval color-grounding ≥90%, bin drop, prompt-follow | — |
| 7 | **PHASE B**: remaining 10 destinations + rack/bin shifts + full diversity (§3 checklist); v5 = merge(pilot, B); ~500 eps (total ~700-800 with top-up) | 6 passes |
| 8 | Train v5 (frozen + unfrozen variants), val split (§5.2); build `ee/assess.py` meanwhile (license!) | — |
| 9 | Eval per-destination×color (auto-scored) → **TOP UP weak cells** +25-50 eps → retrain | — |
| 10 | If camera-shift pain persists: A/B **pi0_fast**; pilot **FTM** one-demo repair | 9 done |
| 11 | Phase 3 (optional): HIL-SERL self-improvement, alternate-direction task (§6) | 10 good |

**Standing safety rules:** watchdog stays ON; never touch IK seeding (`--ik-seed-last`,
`--ik-prev-solution` destroyed a servo); e-stop within reach on any new config; safe motion
config = async + 1-Euro (0.3/0.02).
