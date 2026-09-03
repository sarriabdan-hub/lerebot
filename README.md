# SO-101 Vial Transfer — Imitation Learning (v1)

Teleoperated data collection, ACT training, and autonomous evaluation for a vial
pick-and-place task on a Waveshare SO-101 arm driven by an NVIDIA Jetson AGX Thor.
This README is the operational reference for the v1 campaign; the full environment
build (CUDA, PyTorch, calibration) lives in [`SO101_LeRobot_Setup.md`](SO101_LeRobot_Setup.md).

<!-- Optional: a short GIF loop of the task makes a great header.
![Vial transfer demo](docs/images/demo.gif) -->

## Contents

- [The task](#the-task)
- [Hardware and scene](#hardware-and-scene)
- [The annotated reference episode](#the-annotated-reference-episode)
- [Data collection](#data-collection)
  - [Teleoperation (no recording)](#teleoperation-no-recording)
  - [Session 1 (creates the dataset)](#session-1-creates-the-dataset)
  - [Sessions 2–4 (append with resume)](#sessions-24-append-with-resume)
- [Data quality check (QC)](#data-quality-check-qc)
- [EE-delta action space + π0 VLA](#ee-delta-action-space--π0-vla)
  - [EE-space teleoperation](#ee-space-teleoperation)
  - [EE trajectory test](#ee-trajectory-test)
  - [EE-space recording](#ee-space-recording)
  - [π0 LoRA training](#0-lora-training)
- [Troubleshooting](#troubleshooting)

## The task

The robot picks a **red vial** out of the left rack and places it in **position 3 of the
right rack**. Two 6×1 racks sit side by side, taped to the table. A **blue vial** sits
permanently in position 1 of the right rack as a distractor and never moves. Every other
hole stays empty — there are no partial or in-between states.

The red vial's starting hole is the only thing that changes during data collection. The
destination is always right-rack position 3, so the policy learns to generalize over
*where it picks up* but not *where it places* — a deliberate, contained scope for a first
version.

A subtle but important point drives the whole data-collection design: this project trains
an **ACT** policy, which conditions only on the camera images and the arm's joint state.
**It never reads the language prompt.** The task string is stored as dataset metadata, but
the network doesn't see it during training or inference. So the prompt is a single fixed
sentence across every session, and the robot learns to find the vial *purely from what the
cameras show it*. The generalization you get comes from physically varying the vial's start
position across episodes — not from changing any words. (If you later want the prompt to
actually steer behavior, that calls for a language-conditioned policy such as SmolVLA or
pi0, not ACT.)

The fixed prompt, used verbatim in all sessions and at inference:

```
Place the red vial in position 3 of the right rack.
```

## Hardware and scene

| Component | Detail |
|---|---|
| Arms | Waveshare SO-101, leader + follower, 6 DOF, STS3215 12V motors |
| Compute | NVIDIA Jetson AGX Thor, Ubuntu 24.04 (JetPack 7), MAXN |
| Serial | follower `/dev/ttyACM0`, leader `/dev/ttyACM1` |
| `cam_top` | Waveshare IMX335 USB, top-down, USB port 4.2.2 |
| `cam_wrist` | Waveshare IMX335 USB, gripper-mounted, USB port 4.2.4 |
| `cam_side` | Intel RealSense, 45° side, serial `052622071016` |

The cameras and racks are taped at fixed positions and the lighting is locked, because ACT
trains on pixels: the scene the cameras see *is* the training distribution, and any drift
between recording and inference degrades accuracy. The reference photos below exist so the
exact scene can be restored if anything is bumped or the rig is rebuilt.

USB `/dev/videoN` numbers shift between reboots, so the two IMX335 cameras are always
addressed by their physical-port `/dev/v4l/by-path/...` nodes and the RealSense by its
serial. The IMX335s must run `"fourcc": "MJPG"` and the RealSense needs `"warmup_s": 3`,
or the RealSense times out when all three cameras share the USB bus.

### Reference photos

Commit these to `docs/images/` and they render below. They document the rig precisely
enough to rebuild it: each camera's mount and angle, the racks taped down with hole
positions visible, the arm in its home pose, and — most importantly — a still from each
camera's actual feed, since those frames define the visual distribution the policy learns.

<p><img src="docs/images/rig_overview.jpg" alt="Overall rig and lighting" height="400"></p>

### Physical camera placement

These show each camera clamped in its real-world position and angle — the reference
for re-mounting any camera to the exact same spot if it gets bumped or moved.

<p><img src="docs/images/cam-top-mount.jpg" alt="cam_top physical mount and angle" height="350"></p>

<p><img src="docs/images/cam-wrist-mount.jpg" alt="cam_wrist physical mount on gripper" height="350"></p>

<p><img src="docs/images/cam-side-mount.jpg" alt="cam_side physical mount and angle" height="350"></p>

### Camera view

These show each camera's view.

<p><img src="docs/images/cam_top_view.jpg" alt="Top camera feed (cam_top)" height="350"></p>

<p><img src="docs/images/cam_wrist_view.jpg" alt="Wrist camera feed (cam_wrist)" height="350"></p>

<p><img src="docs/images/cam_side_view.jpg" alt="Side camera feed (cam_side)" height="350"></p>


The cleanest way to capture the three feed stills is to screenshot the Rerun window during
a dry run with `--display_data=true`:

<p><img src="docs/images/rerun_setup.jpg" alt="Rerun live view during recording" height="450"></p>

## The annotated reference episode

One clean episode serves as the gold standard that every other episode — across all
sessions and operators — is checked against. Record it, then replay it through the dataset
visualizer (which opens Rerun with all three camera streams and the joint traces on a shared
timeline) and screen-capture the replay with OBS:

```bash
lerobot-dataset-viz \
    --repo-id=sari/vial_rack_dryrun \
    --root=/home/robot/my_local_data_dryrun6 \
    --episode-index=0
```

The reference video walks through the eight phases of a good demonstration: home pose,
approach to the left rack, descend and grasp, lift clear, transport to the right rack, align
over position 4, lower and release, and retract back to the same home pose. A clean episode
has the gripper fully seated on the vial before lifting, never clips the blue distractor,
moves smoothly without stalls, and ends in the identical home pose it started from. Anything
that misses that bar gets re-recorded with the ← key during collection.

<!-- Video embed. Two options:
  (A) Edit this README on github.com, drag the .mp4 into the editor; GitHub
      inserts an inline player. Limit: 10 MB free / 100 MB paid plans.
  (B) Commit the file to docs/video/ and use the thumbnail link below. -->

<p><a href="https://github.com/sarriabdan-hub/lerebot/raw/main/docs/video/annotated_episode.mp4"><img src="docs/images/episode_thumb.jpg" alt="Watch the annotated reference episode" width="500"></a></p>

## Data collection

The dataset is 100 episodes built from four 25-episode sessions, with at least a 30-minute
break between sessions. The prompt and destination stay constant; only the red vial's
physical start hole changes per session. Session 1 starts it in left-rack position 1,
session 2 in position 3, session 3 in position 4, and session 4 in position 5. Because the
policy only ever sees those four starting positions, evaluation should start the vial in one
of them — positions 2 and 6 are untrained, and the discrete rack holes sit too far apart to
count on ACT interpolating to a hole it never saw.

All four sessions write to the **same dataset**: session 1 creates it, and sessions 2–4
append by reusing the identical `--dataset.repo_id` and `--dataset.root` with the added
`--resume=true` flag. Calibration is treated as a locked variable for the whole campaign —
do not recalibrate mid-collection.

Before any session, set device permissions:

```bash
conda activate lerobot
sudo chmod 666 /dev/ttyACM*
sudo chmod 666 /dev/video*
```

During recording, **→** ends and saves the current episode, **←** discards and re-records
it, and **ESC** stops the session.

### Teleoperation (no recording)

Use this to warm up or check the rig before a session. Nothing is saved.

```bash
lerobot-teleoperate \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=so_follower \
    --robot.calibration_dir=/home/robot/dev/lerebot/calibration/robots/so_follower \
    --robot.cameras='{"cam_top": {"type": "opencv", "index_or_path": "/dev/v4l/by-path/platform-a80aa10000.usb-usb-0:4.2.2:1.0-video-index0", "fps": 30, "width": 640, "height": 480, "fourcc": "MJPG"}, "cam_wrist": {"type": "opencv", "index_or_path": "/dev/v4l/by-path/platform-a80aa10000.usb-usb-0:4.2.4:1.0-video-index0", "fps": 30, "width": 640, "height": 480, "fourcc": "MJPG"}, "cam_side": {"type": "intelrealsense", "serial_number_or_name": "052622071016", "fps": 30, "width": 640, "height": 480, "warmup_s": 3}}' \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyACM1 \
    --teleop.id=so_leader \
    --teleop.calibration_dir=/home/robot/dev/lerebot/calibration/teleoperators/so_leader \
    --display_data=true
```

`--display_data=true` opens Rerun with all three camera feeds and joint state traces on a shared timeline.

### Session 1 (creates the dataset)

Red vial starts in left-rack position 1.

```bash
lerobot-record \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=so_follower \
    --robot.calibration_dir=/home/robot/dev/lerebot/calibration/robots/so_follower \
    --robot.cameras='{"cam_top": {"type": "opencv", "index_or_path": "/dev/v4l/by-path/platform-a80aa10000.usb-usb-0:4.2.2:1.0-video-index0", "fps": 30, "width": 640, "height": 480, "fourcc": "MJPG"}, "cam_wrist": {"type": "opencv", "index_or_path": "/dev/v4l/by-path/platform-a80aa10000.usb-usb-0:4.2.4:1.0-video-index0", "fps": 30, "width": 640, "height": 480, "fourcc": "MJPG"}, "cam_side": {"type": "intelrealsense", "serial_number_or_name": "052622071016", "fps": 30, "width": 640, "height": 480, "warmup_s": 3}}' \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyACM1 \
    --teleop.id=so_leader \
    --teleop.calibration_dir=/home/robot/dev/lerebot/calibration/teleoperators/so_leader \
    --dataset.repo_id=sari/vial_rack_v1 \
    --dataset.single_task="Place the red vial in position 3 of the right rack." \
    --dataset.num_episodes=25 \
    --dataset.episode_time_s=30 \
    --dataset.reset_time_s=15 \
    --dataset.root=/home/robot/my_local_data_v1 \
    --dataset.push_to_hub=False \
    --display_data=true
```

### Sessions 2–4 (append with resume)

Identical to session 1, but move the red vial to that session's start hole (position 3, 4,
then 5) and add `--resume=true`. Keep `--dataset.repo_id` and `--dataset.root` exactly the
same so the episodes accumulate in one dataset:

```bash
lerobot-record \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=so_follower \
    --robot.calibration_dir=/home/robot/dev/lerebot/calibration/robots/so_follower \
    --robot.cameras='{"cam_top": {"type": "opencv", "index_or_path": "/dev/v4l/by-path/platform-a80aa10000.usb-usb-0:4.2.2:1.0-video-index0", "fps": 30, "width": 640, "height": 480, "fourcc": "MJPG"}, "cam_wrist": {"type": "opencv", "index_or_path": "/dev/v4l/by-path/platform-a80aa10000.usb-usb-0:4.2.4:1.0-video-index0", "fps": 30, "width": 640, "height": 480, "fourcc": "MJPG"}, "cam_side": {"type": "intelrealsense", "serial_number_or_name": "052622071016", "fps": 30, "width": 640, "height": 480, "warmup_s": 3}}' \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyACM1 \
    --teleop.id=so_leader \
    --teleop.calibration_dir=/home/robot/dev/lerebot/calibration/teleoperators/so_leader \
    --dataset.repo_id=sari/vial_rack_v1 \
    --dataset.single_task="Place the red vial in position 3 of the right rack." \
    --dataset.num_episodes=25 \
    --dataset.episode_time_s=30 \
    --dataset.reset_time_s=15 \
    --dataset.root=/home/robot/my_local_data_v1 \
    --dataset.push_to_hub=False \
    --display_data=true \
    --resume=true
```

After session 2 finishes, confirm the episodes appended on top (you should have episodes
25–49, not a fresh 0–24) before committing to sessions 3 and 4. The exact `num_episodes`
semantics on resume are the one behavior worth verifying on your own LeRobot build, and
catching a problem after 50 episodes is much cheaper than after 75.

To inspect the dataset at any point:

```bash
lerobot-dataset-viz \
    --repo-id=sari/vial_rack_v1 \
    --root=/home/robot/my_local_data_v1 \
    --episode-index=0
```

If the Rerun panels come up black or show a stale layout, right-click the Blueprint panel
and choose Reset to rebuild them from the current data.

## Data quality check (QC)

Every session is verified with `qc_dataset_v3.py` before proceeding to the next. The
script checks camera frame coverage, joint discontinuities, stream sync, language
annotation, and aggregate stats, and outputs a per-episode pass/fail JSON + Markdown
report.

**Calibrated threshold for this setup:** the LeRobot recorder captures slightly more
video than joint state rows per episode — the camera keeps running for 1–9 s after
the data recording ends. This is normal behaviour on this build. The `--frame-drop-pct`
threshold is set to 60 to reflect this; it still catches a genuinely truncated video
while not false-failing clean episodes.

Run after each session, incrementing the output filename:

```bash
cd /home/robot/dev/lerebot
python qc_dataset_v3.py \
    --dataset-root /home/robot/my_local_data_v1 \
    --out qc_reports/qc_report_s1.json \
    --md qc_reports/qc_report_s1.md \
    --frame-drop-pct 60
```

QC results for all four sessions are saved in `qc_reports/`. **Final result: 100/100
episodes passed.**

> **On cross-stream sync:** the script verifies that joint state timestamps are evenly
> spaced (drift < 30 ms from 1/fps). In the v3.0 consolidated-video format, per-frame
> camera timestamps are not stored, so camera–joint alignment cannot be verified
> frame-by-frame from the data on disk. The sync guarantee comes from `lerobot-record`
> controlling both streams in the same control loop.

## EE-delta action space + π0 VLA

The π0 VLA operates in end-effector
(EE) space, controlled via Cartesian coordinates rather than raw motor angles —
the interface a language-conditioned policy outputs.

All scripts live in `ee/`. URDF: `SO101/so101_new_calib.urdf`.

### EE-space teleoperation

Drives the follower in EE space without recording anything. Leader joints → FK → EE pose →
safety bounds → IK → follower joints, all at 30fps.

```bash
conda activate lerobot
sudo chmod 666 /dev/ttyACM*
python ee/teleoperate.py
```

### EE trajectory test

Verifies the IK pipeline with a hand-coded pick-and-place sequence. Run `--probe` first
to record your real rack positions (motors go limp; push arm by hand), then `--run` to
execute and verify each waypoint via FK.

```bash
conda activate lerobot
sudo chmod 666 /dev/ttyACM*
python ee/trajectory_test.py --probe   # saves ee/waypoints.json + ee/joint_waypoints.json
python ee/trajectory_test.py --run     # executes 7-waypoint trajectory, prints PASS/FAIL
```

Results on this rig: home 2.1mm, above_vial 2.1mm, grasp 5.1mm, lift 15.8mm,
above_rack 24.8mm, place 7.9mm, retract 1.5mm — **ALL PASS**.

### EE-space recording

Records episodes with 7D EE-space actions for π0 training. Same controls as joint-space
recording (→ save, ← re-record, ESC stop).

```bash
conda activate lerobot
sudo chmod 666 /dev/ttyACM*
python ee/record.py
# writes to /home/robot/my_local_data_v1_ee → HuggingFace: sari-abdan/vial-sort-v1-ee
```

### π0 LoRA training

Training runs on the **workstation** (NVIDIA RTX 6000 Ada, 48GB), not on Thor.

**One-time setup on workstation:**
```bash
# 1. Install deps
pip install -e ".[pi0,training]"

# 2. Copy URDF from Thor
scp -r robot@192.168.123.198:/home/robot/dev/lerebot/SO101/ ./SO101/
scp -r robot@192.168.123.198:/home/robot/dev/lerebot/ee/ ./ee/

# 3. Download dataset
hf download sari-abdan/vial-sort-v1-static --repo-type dataset --local-dir ./data/vial-sort-v1-static

# 4. Convert joint → EE (one-time, ~5 min)
python ee/convert_dataset.py
# output: ./data/vial-sort-v1-ee  (7D EE actions, 100 eps)
```

**Smoke test (verify no crash, ~5 min):**
```bash
bash ee/smoke_test.sh
# 50 steps, 10 episodes, LoRA rank 16 — checkpoint at outputs/train/smoke_test/
```

**Full training (~several hours):**
```bash
bash ee/train_pi0_lora.sh
# 30k steps, batch 8, bfloat16 — checkpoints at outputs/train/vial-sort-pi0-lora/ every 5k steps
```

Smoke test result: 50 steps, loss 0.406, 1.4M LoRA params / 4B total (0.034% trained),
clean exit, checkpoint saved. ✓

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Failed to open OpenCVCamera(/dev/videoN)`, then `'NoneType' has no attribute 'is_set'` | raw `/dev/videoN` renumbered; the `is_set` error is just cleanup after the real failure | use the `/dev/v4l/by-path/...` nodes |
| `failed to set fourcc=MJPG (actual=UYVY)` on a supposed IMX335 | raw node points at the wrong device (UYVY is the RealSense) | use by-path nodes; verify with `ls /dev/v4l/by-path/` |
| RealSense `Timed out waiting for frame` with all 3 cams | USB bandwidth | `"fourcc": "MJPG"` on the IMX335s, `"warmup_s": 3` on the RealSense |
| `Permission denied: /dev/ttyACM0` | serial permissions | `sudo chmod 666 /dev/ttyACM*` (or add user to `dialout`) |
| `Cannot save file into a non-existent directory` | `~` not expanded in `--dataset.root` | use an absolute `/home/robot/...` path |
| `Repo id must be in the form...` for `policy.path` | relative path | absolute path to `pretrained_model` |
| `dataset name does not begin with 'eval_'` | inference dataset name | prefix with `eval_` |
| Resume restarted at episode 0 | wrong repo_id/root or missing flag | keep repo_id and root identical, add `--resume=true` |
| No checkpoint after training | `save_freq` greater than `steps` | set `--save_freq` ≤ `--steps` |
