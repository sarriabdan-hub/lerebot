#!/usr/bin/env bash
# ============================================================================
#  v5 PILOT RECORDING — one RUN at a time (5 episodes, one label)
#  Reads the label for the run straight out of ee/initial_fable_v5.txt, so a
#  label can never be mismatched to its run by hand.
#
#  RUN ON THOR:
#     bash ee/record_v5.sh 1        # RUN 01 -> CREATES the dataset
#     bash ee/record_v5.sh 2        # RUN 02 -> appends (--resume=true)
#     ...                           # 10 runs = 50 episodes
#
#  Before each run, read that run's per-episode vial layout:
#     bash ee/record_v5.sh 3 --show
#
#  Controls while recording:  ->  save & next | <-  redo episode | ESC stop
#  HOME the arm before EVERY episode. Sources only from slots 1/3/4/6.
# ============================================================================

set -euo pipefail

RUN_N="${1:-}"
if [ -z "$RUN_N" ]; then
  echo "usage: bash ee/record_v5.sh <run number 1..60> [--show]"
  exit 1
fi

LEREBOT="${LEREBOT:-/home/robot/dev/lerebot}"
SHEET="${SHEET:-$LEREBOT/ee/SORT_SHEET_v5.md}"
ROOT="${ROOT:-/home/robot/my_local_data_v5}"
REPO_ID="${REPO_ID:-sari-abdan/vial-sort-v5-pilot}"
EPISODES="${EPISODES:-5}"

# total run count is read from the sheet itself (works for /40, /60, whatever)
TOTAL_RUNS=$(grep -cE '^RUN ' "$SHEET")
RUN_TAG=$(printf 'RUN %02d/%02d' "$RUN_N" "$TOTAL_RUNS")

# ── pull this run's label + episode block out of the sheet ──────────────────
LABEL=$(grep -m1 "^$RUN_TAG" "$SHEET" | sed 's/.*"\(.*\)".*/\1/')
if [ -z "$LABEL" ]; then
  echo "ERROR: '$RUN_TAG' not found in $SHEET"; exit 1
fi

echo "============================================================"
echo " $RUN_TAG"
echo " label: \"$LABEL\""
echo "============================================================"
echo " scene per episode (set the vials EXACTLY like this):"
awk -v tag="^$RUN_TAG" '$0 ~ tag {f=1; next} /^RUN /{f=0} f && /ep [0-9]/' "$SHEET"
echo "------------------------------------------------------------"

# --show = print the plan and stop (no robot, no recording)
if [ "${2:-}" = "--show" ]; then exit 0; fi

# ── resume logic: run 1 creates, everything after appends ──────────────────
RESUME_FLAG=""
if [ -e "$ROOT" ]; then
  RESUME_FLAG="--resume=true"
  HAVE=$(python - "$ROOT" <<'PY' 2>/dev/null || echo "?"
import json,sys
print(json.load(open(f"{sys.argv[1]}/meta/info.json"))["total_episodes"])
PY
)
  echo "[v5] dataset exists with $HAVE episodes -> APPENDING (--resume=true)"
  EXPECT=$(( (RUN_N - 1) * EPISODES ))
  if [ "$HAVE" != "?" ] && [ "$HAVE" -ne "$EXPECT" ]; then
    echo "[v5] !! WARNING: expected $EXPECT episodes before $RUN_TAG, found $HAVE."
    echo "[v5]    A run was skipped/redone. Ctrl+C now if that's wrong."
    sleep 5
  fi
else
  if [ "$RUN_N" -ne 1 ]; then
    echo "[v5] !! No dataset at $ROOT but this is run $RUN_N — start with run 1."
    exit 1
  fi
  echo "[v5] creating a NEW dataset at $ROOT"
fi

# the VLA server holds the cameras + motor bus — it must not be running
if pgrep -f "ee/vla_server.py" >/dev/null; then
  echo "[v5] stopping vla_server (holds the cameras + motor bus)..."
  pkill -f "ee/vla_server.py" || true; sleep 3
fi

# ── cameras: 3 RGB + DEPTH on the D435i ────────────────────────────────────
# cam_top/cam_wrist are by-path pinned (DO NOT MOVE THEM); MJPG avoids the USB
# bandwidth starvation that once pinned the RealSense to USB2.
CAMS='{"cam_top": {"type": "opencv", "index_or_path": "/dev/v4l/by-path/platform-a80aa10000.usb-usb-0:4.2.2:1.0-video-index0", "fps": 30, "width": 640, "height": 480, "fourcc": "MJPG"}, "cam_wrist": {"type": "opencv", "index_or_path": "/dev/v4l/by-path/platform-a80aa10000.usb-usb-0:4.2.4:1.0-video-index0", "fps": 30, "width": 640, "height": 480, "fourcc": "MJPG"}, "cam_side": {"type": "intelrealsense", "serial_number_or_name": "052622071016", "fps": 30, "width": 640, "height": 480, "warmup_s": 3, "use_depth": true}}'

# ── the settings MEASURED to hold a clean 30 Hz with 4 streams (2026-07-18) ─
#   display_data=false  <- THE fix. The rerun viewer rendering 4 live streams
#                          was the CPU hog causing every "loop slower" warning.
#   streaming_encoding=false <- measured WORSE (moves encoding into the capture
#                          loop). Batch-encode between episodes instead.
#   2 encoder / 2 writer threads per camera <- less contention on ARM cores.
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
  --dataset.push_to_hub=False \
  --display_data="${DISPLAY_DATA:-false}" \
  --dataset.streaming_encoding=false \
  --dataset.encoder_threads=2 \
  --dataset.num_image_writer_threads_per_camera=2 \
  --dataset.single_task="$LABEL" \
  $RESUME_FLAG

# ── post-run check ─────────────────────────────────────────────────────────
echo
echo "=================== AFTER $RUN_TAG ==================="
python - "$ROOT" <<'PY' || true
import json, sys
info = json.load(open(f"{sys.argv[1]}/meta/info.json"))
print("total episodes:", info["total_episodes"])
streams = [k for k in info["features"] if "image" in k]
print("image streams :", streams)
print("depth present :", "YES" if any("cam_depth" in s for s in streams) else ">>> NO <<<")
PY
NEXT=$((RUN_N + 1))
echo "next:  bash ee/record_v5.sh $NEXT        (preview: ... $NEXT --show)"
if [ $((RUN_N % 5)) -eq 0 ]; then
  echo
  echo ">>> SESSION COMPLETE ($((RUN_N / 5)) of 8). Run the label audit NOW (same day):"
  echo "    python $LEREBOT/ee/audit_labels.py --root $ROOT --group"
fi
echo "======================================================"
