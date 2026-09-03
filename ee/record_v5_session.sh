#!/usr/bin/env bash
# ============================================================================
#  v5 SESSION DRIVER — chains record_v5.sh runs BACK-TO-BACK.
#  One command per 25-episode session; between runs it shows you the next
#  run's prompt + per-episode vial layout and waits for ENTER.
#
#  RUN ON THOR:
#     bash ee/record_v5_session.sh 1 5     # session 1 = runs 1..5  (eps 0-24)
#     bash ee/record_v5_session.sh 6 10    # session 2 = runs 6..10 (eps 25-49)
#
#  Each run still records its 5 episodes with the sheet's own label
#  (that part is a lerobot-record constraint: one invocation = one label).
#  Ctrl+C anytime aborts cleanly; rerun with the run number it stopped at.
# ============================================================================

set -euo pipefail

START="${1:-}"; END="${2:-}"
if [ -z "$START" ] || [ -z "$END" ]; then
  echo "usage: bash ee/record_v5_session.sh <first run> <last run>"
  echo "   session 1: bash ee/record_v5_session.sh 1 5"
  echo "   session 2: bash ee/record_v5_session.sh 6 10"
  exit 1
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
LEREBOT="${LEREBOT:-/home/robot/dev/lerebot}"
ROOT="${ROOT:-/home/robot/my_local_data_v5}"

for N in $(seq "$START" "$END"); do
  clear 2>/dev/null || true
  echo
  echo "####################################################################"
  echo "##  NEXT: RUN $N of $END   (5 episodes)"
  echo "####################################################################"
  # show the prompt + scene layout for this run (no robot yet)
  bash "$HERE/record_v5.sh" "$N" --show
  echo
  echo ">>> SET UP THE SCENE for the FIRST episode above."
  echo ">>> HOME the arm. Then press ENTER to start recording run $N"
  echo ">>> (or Ctrl+C to stop the session here)."
  read -r
  bash "$HERE/record_v5.sh" "$N"
  echo
  echo "=== run $N done. Take a breath. ==="
done

echo
echo "####################################################################"
echo "##  SESSION COMPLETE (runs $START-$END)."
echo "##  RUN THE LABEL AUDIT NOW (same day!):"
echo "##     python $LEREBOT/ee/audit_labels.py --root $ROOT --group"
echo "####################################################################"
