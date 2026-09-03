# isaac/ — vial-sort v5 in Isaac Sim (SO-101, sim twin of the real rig)

The real follower arm is down (shoulder_lift ST3215 burnout, see `ee/PLAN_FABLE.md`).
This directory is a **sim twin of the vial-sort setup** so the v5 pilot can proceed on
the workstation. DEFAULT SCENE = EXACT V4 REPLICA (calibrated against real v4
dataset frames): SO-101 on a table, two BLACK elevated rail-style 6-slot racks in a
slight V opening toward the arm (arm behind the middle gap), NO bin, tall red test
tubes — so the v4 pi0.5 checkpoint / dataset can be replayed and evaluated in sim
1:1. Pass `--with-bin` for the v5 pilot scene (bin at the side), colored
vials (RED / CYAN / DARK-GREEN / LIGHT-PURPLE), and the three cameras with the **exact
real dataset keys**: `cam_top`, `cam_wrist`, `cam_side` (640×480 @ 30 fps).

The **real leader arm** (plugged into this WS over USB) teleoperates the sim follower.
Episode scenes + prompts come straight from `ee/initial_fable_v5.txt` (parsed, never
modified) — and unlike the real rig, **scene setup is automatic**: vials teleport into
the sheet's slots and the arm homes itself every episode.

Nothing in here touches `ee/` or the rest of the repo.

## Files

| file | what |
|---|---|
| `sim_config.py` | ALL geometry/cameras/gains/home-pose constants (things marked `TUNE` are the knobs) |
| `sheet.py` | parser for `ee/initial_fable_v5.txt` (200 pilot episodes) — verified: 70 BIN / 65 L1 / 65 R3, 50 per color |
| `scene.py` | Isaac Lab scene: table, SO-101 from `SO101/so101_new_calib.urdf`, racks, bin, vial pool, 3 cameras |
| `smoke_test.py` | build scene, stage an episode, wave arm, dump one PNG per camera to `isaac/out/` |
| `teleop_record.py` | real leader → sim follower, writes a LeRobotDataset (same schema as real raw recordings) |
| `eval_pi05.py` | roll out a pi0/pi0.5 checkpoint in sim (EE-action path identical to `ee/rollout_pi0_lora.py`, incl. FK/IK on the same URDF) |

## Install (on this WS — RTX 6000 Pro Blackwell is fully supported by Isaac Sim 5.x)

Isaac Sim 5.x runs on **Python 3.11** (lerobot pins 3.12+, so it gets its own env;
we install lerobot into it with `--ignore-requires-python`, which works fine in practice).
NVIDIA driver ≥ 570 required for Blackwell — check with `nvidia-smi` first.

No conda on this WS and Ubuntu 24.04 ships Python 3.12, so use **uv** — it downloads
a standalone Python 3.11 by itself:

```bash
# 0) uv (one-time)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env        # or open a new terminal

# 1) dedicated 3.11 env (--seed adds pip, which isaaclab.sh and step 4 need)
uv venv ~/isaac-venv --python 3.11 --seed
source ~/isaac-venv/bin/activate

# 2) Isaac Sim 5.x (pip, ~10 GB download; EULA prompt on first run)
uv pip install "isaacsim[all,extscache]==5.1.0" --extra-index-url https://pypi.nvidia.com

# 3) Isaac Lab (matching release branch) — installs into the ACTIVE venv
cd ~ && git clone https://github.com/isaac-sim/IsaacLab.git && cd IsaacLab
./isaaclab.sh --install none        # core isaaclab pkgs only, no RL frameworks needed

# 4) lerobot (this repo) into the same env, for the leader arm + dataset writer
#    (plain pip here: --ignore-requires-python bypasses lerobot's >=3.12 pin)
pip install --ignore-requires-python -e /home/sari/lerobot
pip install feetech-servo-sdk pynput placo "imageio[ffmpeg]" pillow

# 5) leader arm USB permission (once)
sudo usermod -aG dialout $USER   # then re-login
```

Every later session: just `source ~/isaac-venv/bin/activate`.

First launch compiles shaders — expect a few minutes; later runs are fast.

## Run order

```bash
cd /home/sari/lerobot/isaac
source ~/isaac-venv/bin/activate

# 1) SMOKE TEST — check the scene + tune camera poses
python smoke_test.py --headless          # writes out/cam_{top,side,wrist}.png
#   Compare the PNGs to the real reference frames (ee/extract_ref_frame.py output)
#   and adjust CAM_TOP / CAM_SIDE / CAM_WRIST in sim_config.py until they roughly
#   match the real views. Run without --headless to inspect the scene in the GUI.

# 2) TELEOP RECORD the pilot (plug in the LEADER arm; find the port with
#    `ls /dev/ttyACM*` — with only the leader plugged in it'll be /dev/ttyACM0)
python teleop_record.py --leader-port /dev/ttyACM0 \
    --root ~/sim_data_v5_pilot --repo-id sari-abdan/vial-sort-v5-sim-pilot
#   → arrow-right saves, arrow-left re-records, ESC stops; resume-aware like
#     ee/record.py: rerun the same command for the next 25-episode session.
#   Recording is JOINT-space raw; afterwards run the usual joint→EE conversion +
#   paraphrase + train flow from ee/ (convert_dataset.py — remember the stats
#   'count' fix — then paraphrase_tasks.py, then train per PLAN_FABLE).

# 2b) OR record the ORIGINAL v4 task instead of the v5 pilot — same racks,
#     ONE red vial (source auto-placed on the opposite rack, anchors 1/3/4/6),
#     exact v4 grammar, destinations interleaved (left 1/3/6 + right 6):
python teleop_record.py --v4 --v4-eps-per-dest 30 --leader-port /dev/ttyACM0 \
    --root ~/sim_data_v4 --repo-id sari-abdan/vial-sort-v4-sim

# 3) EVAL a trained checkpoint in sim (auto-staged scenes from the sheet)
python eval_pi05.py --checkpoint /path/to/checkpoints/012000/pretrained_model \
    --episode 3 --headless --save-video out/rollout_ep3.mp4
#   --joint-space if the checkpoint was trained on raw joints instead of EE.
#   --n-action-steps 15 to match the real deployment setting.
#   --v4 stages a v4-style single-red-vial episode instead of the v5 sheet.
```

## Robometer as the sim success judge

`eval_pi05.py --save-video x.mp4` also writes `x.json` (task, episode, dest, checkpoint).
Robometer is already vendored at `ee/robometer/` with a local inference script that takes
exactly a video + instruction — run it in Robometer's own env (its deps differ from Isaac's):

```bash
# score one sim rollout (per-frame progress + success probability)
cd /home/sari/lerobot/ee/robometer
python scripts/example_inference_local.py \
    --model-path aliangdw/qwen4b_pref_prog_succ_8_frames_all_part2 \
    --video /home/sari/lerobot/isaac/out/rollout_ep3.mp4 \
    --task "$(python -c "import json;print(json.load(open('/home/sari/lerobot/isaac/out/rollout_ep3.json'))['task'])")"
```

Loop over episodes → mp4+json → Robometer verdicts = the auto-scored eval sweep from
PLAN_FABLE §4b/§5.3, no arm and no manual outcome buttons. Caveat: Robometer's SO-101
exposure is real-camera footage; validate it on ~10 sim rollouts with known outcomes
(hand-judged) before trusting it as the sweep metric — same ≥85%-agreement gate as the
real-data pilot.

## Sim ↔ real notes / expected tuning

- **Leader calibration**: the leader uses its normal lerobot calibration
  (`--calibration-dir` if yours isn't in the default location). If you've never
  calibrated this leader on this machine, run lerobot's calibrate flow once.
- **Camera poses are eyeballed** (`TUNE` marks in `sim_config.py`). The wrist-cam
  offset/rotation especially will need a few smoke-test iterations.
- **Drive gains** (`DRIVE_STIFFNESS/DAMPING`): raise stiffness if the sim arm lags the
  leader, raise damping if it oscillates.
- **Gripper**: leader sends 0–100; mapped linearly onto the URDF gripper joint limits.
- **Sim-vs-real gap**: a policy trained purely on sim data will NOT transfer to the real
  arm without domain randomization/fine-tuning — this sim's near-term value is (a) keep
  recording/eval pipelines and prompts moving while the servo is replaced, (b) cheap
  pi0.5 pipeline validation (color grounding, bin drops, prompt-following at 200 eps),
  (c) later, sim-augmented pretraining ahead of a small real-data re-anchor.
- Physics runs at 120 Hz, control/cameras at 30 Hz (`DECIMATION=4`), matching real FPS.
