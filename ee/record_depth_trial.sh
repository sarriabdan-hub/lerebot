#!/usr/bin/env bash
# Depth trial — 10 throwaway episodes into their OWN dataset, purely to prove
# the RealSense depth stream is actually being recorded. NOT v5 pilot data.
#
# PREREQ (already done on Thor 2026-07-18): so_follower.py patched by
# ee/patch_depth_camera.py — verify with:
#     grep -n colorize_depth <lerobot>/src/lerobot/robots/so_follower/so_follower.py
# (must print the helper + the get_observation emit).
#
# RUN ON THOR:   bash ee/record_depth_trial.sh
# Override anything:  EPISODES=5 ROOT=/home/robot/foo bash ee/record_depth_trial.sh
#
# Controls while recording:  ->  save & next | <-  redo episode | ESC stop

set -euo pipefail

EPISODES="${EPISODES:-10}"
ROOT="${ROOT:-/home/robot/depth_trial_pi05}"
REPO_ID="${REPO_ID:-sari-abdan/depth-trial-pi05}"
TASK="${TASK:-Place the red vial in position 3 of the right rack.}"
LEREBOT="${LEREBOT:-/home/robot/dev/lerebot}"

# Encoder tuning. Adding the 4th (depth) stream is +33% encode/writer work and
# Thor encodes 4x 640x480 AV1 in SOFTWARE on ARM cores -> the "Record loop is
# running slower than 30 Hz" warnings. streaming_encoding overlaps encoding with
# capture instead of blocking at episode-save. Fewer writer threads = LESS
# contention on a Jetson (default is 4 PER CAMERA = 16 threads for 4 cams).
# MEASURED on Thor 2026-07-18: streaming_encoding=true made the loop-rate
# warnings CONTINUOUS (19-30 Hz) instead of only at episode start. It does not
# reduce work, it just moves encoding from "between episodes" to "during
# capture" -> it competes with the record loop. Thor's ARM cores are simply
# saturated. Default it back OFF.
STREAMING="${STREAMING:-false}"
ENC_THREADS="${ENC_THREADS:-2}"
WRITER_THREADS="${WRITER_THREADS:-2}"
# The rerun viewer live-renders ALL 4 camera streams -> real CPU cost on a
# Jetson, and you're watching the actual arm, not the screen. Biggest single
# saving available. DISPLAY=true only when you truly need the viewer.
DISPLAY_DATA="${DISPLAY_DATA:-false}"

# LeRobotDataset.create() refuses to touch an existing dir (FileExistsError).
# This is a THROWAWAY trial dataset, so offer to wipe it — but never silently:
# RESET=1 to auto-wipe, otherwise stop with the exact command to run.
if [ -e "$ROOT" ]; then
  if [ "${RESET:-0}" = "1" ]; then
    echo "[depth-trial] RESET=1 -> removing existing $ROOT"
    rm -rf "$ROOT"
  else
    echo "[depth-trial] ERROR: $ROOT already exists (from the previous trial)."
    echo "               wipe it:      rm -rf $ROOT"
    echo "               or re-run as: RESET=1 EPISODES=$EPISODES bash $0"
    exit 1
  fi
fi

# the VLA server holds the cameras + the motor bus — it must not be running
if pgrep -f "ee/vla_server.py" >/dev/null; then
  echo "[depth-trial] stopping vla_server (it holds the cameras + motor bus)..."
  pkill -f "ee/vla_server.py" || true
  sleep 3
fi

# cam_top/cam_wrist are by-path pinned (DO NOT MOVE THEM), MJPG to avoid the
# USB-bandwidth starvation that killed the RealSense before.
# cam_side = the D435i with use_depth -> the whole point of this trial.
CAMS='{"cam_top": {"type": "opencv", "index_or_path": "/dev/v4l/by-path/platform-a80aa10000.usb-usb-0:4.2.2:1.0-video-index0", "fps": 30, "width": 640, "height": 480, "fourcc": "MJPG"}, "cam_wrist": {"type": "opencv", "index_or_path": "/dev/v4l/by-path/platform-a80aa10000.usb-usb-0:4.2.4:1.0-video-index0", "fps": 30, "width": 640, "height": 480, "fourcc": "MJPG"}, "cam_side": {"type": "intelrealsense", "serial_number_or_name": "052622071016", "fps": 30, "width": 640, "height": 480, "warmup_s": 3, "use_depth": true}}'

echo "[depth-trial] $EPISODES episodes -> $ROOT"
echo "[depth-trial] task: $TASK"

lerobot-record \
  --robot.type=so101_follower --robot.port=/dev/ttyACM0 --robot.id=so_follower \
  --robot.calibration_dir="$LEREBOT/calibration/robots/so_follower" \
  --robot.cameras="$CAMS" \
  --teleop.type=so101_leader --teleop.port=/dev/ttyACM1 --teleop.id=so_leader \
  --teleop.calibration_dir="$LEREBOT/calibration/teleoperators/so_leader" \
  --dataset.repo_id="$REPO_ID" \
  --dataset.root="$ROOT" \
  --dataset.num_episodes="$EPISODES" \
  --dataset.episode_time_s=30 --dataset.reset_time_s=15 \
  --dataset.push_to_hub=False --display_data="$DISPLAY_DATA" \
  --dataset.streaming_encoding="$STREAMING" \
  --dataset.encoder_threads="$ENC_THREADS" \
  --dataset.num_image_writer_threads_per_camera="$WRITER_THREADS" \
  --dataset.single_task="$TASK"

# ── verification: this is the entire reason the trial exists ────────────────
echo
echo "=============== DEPTH CHECK ==============="
ls "$ROOT/videos/" || true
if [ -d "$ROOT/videos/observation.images.cam_depth" ]; then
  echo ">>> PASS: observation.images.cam_depth exists — depth IS being recorded."
else
  echo ">>> FAIL: no cam_depth stream."
  echo "    so_follower.py is not patched (or a different lerobot is on PATH):"
  echo "    grep -n colorize_depth \$(python -c 'import lerobot,os;print(os.path.dirname(lerobot.__file__))')/robots/so_follower/so_follower.py"
fi
python - "$ROOT" <<'PY' || true
import json, sys
info = json.load(open(f"{sys.argv[1]}/meta/info.json"))
print("episodes:", info["total_episodes"])
print("image streams:", [k for k in info["features"] if "image" in k])
PY
echo "==========================================="
echo "Eyeball one depth frame: racks/vials should be distinguishable colour"
echo "bands, BLACK where the glass defeats the sensor. All-black or one flat"
echo "colour => the 0.25-1.20 m range needs retuning."
echo
echo "When done with this throwaway dataset:   rm -rf $ROOT"
