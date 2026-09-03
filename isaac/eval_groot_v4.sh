#!/usr/bin/env bash
# Sim eval sweep for the GR00T N1.5 v4 checkpoints (3k / 5k / 7k) in the Isaac twin.
#
# WHY these three: unfrozen-vision GR00T on 118 eps peaks EARLY (loss flattened by
# ~4k in the training log) — evaluate the early saves first, per PLAN_FABLE / the
# train script caveat. Add 10k only if 7k still improves.
#
# ARCHITECTURE (same split as the real rig): the Isaac scene lives in the isaac-venv
# (py3.11) behind sim_server.py; the policy runs here in the lerobot .venv (py3.12,
# now has the groot deps + the SDPA patch). eval_pi05.py is policy-agnostic
# (get_policy_class from the checkpoint config), so it drives GR00T as-is — the only
# GR00T-specific knob is --n-action-steps 16 (its native chunk regime; pi05 used 15).
#
# CAMERAS/RACKS: calibrated against real v4 frames on 2026-07-08 (cam_side symmetric,
# cam_top arm-on-right, shallow-V racks, no bin, tall red tubes). See sim_config.py.
#
# CAVEAT (read before trusting a number): GR00T-v4 trained with UNFROZEN vision on
# REAL camera pixels. Isaac's renderer (lighting/materials/no fisheye) is a domain
# gap the vision tower never saw, so these sim rollouts test GEOMETRY + LANGUAGE
# plumbing (does "left rack pos 6" drive the arm to the right slot?) and gross grasp
# behaviour — NOT absolute real-robot grasp success. Use it to rank checkpoints and
# sanity-check prompt-following until the shoulder_lift servo is replaced.
#
# RUN
#   # terminal 1 (once): the sim server, in the isaac env —
#   source ~/isaac-venv/bin/activate && python /home/sari/lerobot/isaac/sim_server.py --headless
#   # terminal 2 (repo root): this sweep —
#   bash isaac/eval_groot_v4.sh
# If the server isn't up, this script launches it for you (headless) and waits.

set -euo pipefail
cd "$(dirname "$0")/.."          # repo root

CKPT_ROOT="${CKPT_ROOT:-outputs/train/vial-sort-groot-v4/checkpoints}"
STEPS="${STEPS:-3000 5000 7000}"
# v4 episodes 0..3 = the 4 destinations (left1, left3, left6, right6) at source slot 1;
# 4..7 = same 4 dests at source slot 3. Default = one full destination sweep (0-3).
EPISODES="${EPISODES:-0 1 2 3}"
NSTEPS="${NSTEPS:-16}"            # GR00T native chunk
SECONDS_PER="${SECONDS_PER:-45}"
OUTDIR="${OUTDIR:-isaac/out/groot_v4}"
SIM_HOST="${SIM_HOST:-127.0.0.1}"
SIM_PORT="${SIM_PORT:-6060}"
ISAAC_PY="${ISAAC_PY:-$HOME/isaac-venv/bin/python}"
mkdir -p "$OUTDIR"

# ── ensure the sim server is up ───────────────────────────────────────────────
if ! curl -sf "http://$SIM_HOST:$SIM_PORT/ping" >/dev/null 2>&1; then
  echo "[eval] sim_server not responding on $SIM_PORT — launching headless (isaac-venv)…"
  TMPDIR="$HOME/.cache/isaaclab-tmp" "$ISAAC_PY" isaac/sim_server.py --headless \
      --port "$SIM_PORT" > /tmp/sim_server.log 2>&1 &
  echo "[eval] sim_server pid $! (log: /tmp/sim_server.log) — waiting for Isaac to boot…"
  for _ in $(seq 1 90); do
    curl -sf "http://$SIM_HOST:$SIM_PORT/ping" >/dev/null 2>&1 && break
    sleep 2
  done
  curl -sf "http://$SIM_HOST:$SIM_PORT/ping" >/dev/null 2>&1 \
    || { echo "[eval] sim_server failed to start — see /tmp/sim_server.log"; exit 1; }
fi
echo "[eval] sim_server ready: $(curl -s http://$SIM_HOST:$SIM_PORT/ping)"

# ── sweep ─────────────────────────────────────────────────────────────────────
for step in $STEPS; do
  ckpt="$CKPT_ROOT/$(printf '%06d' "$step")/pretrained_model"
  [ -d "$ckpt" ] || { echo "[eval] MISSING $ckpt — skipping"; continue; }
  for ep in $EPISODES; do
    vid="$OUTDIR/groot_${step}_ep${ep}.mp4"
    echo "=== ckpt $step  ep $ep  ->  $vid ==="
    .venv/bin/python isaac/eval_pi05.py \
      --checkpoint "$ckpt" \
      --v4 --episode "$ep" \
      --n-action-steps "$NSTEPS" \
      --seconds "$SECONDS_PER" \
      --sim-host "$SIM_HOST" --sim-port "$SIM_PORT" \
      --save-video "$vid"
  done
done

# ── build a Robometer manifest (video,task) from the .json sidecars ───────────
MANIFEST="$OUTDIR/manifest.csv"
.venv/bin/python - "$OUTDIR" "$MANIFEST" <<'PY'
import csv, glob, json, sys
outdir, manifest = sys.argv[1], sys.argv[2]
rows = []
for j in sorted(glob.glob(f"{outdir}/*.json")):
    m = json.load(open(j))
    rows.append((m["video"], m["task"]))          # ground_truth left blank -> fill after eyeballing
with open(manifest, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["video", "task", "ground_truth"])
    for v, t in rows: w.writerow([v, t, ""])
print(f"wrote {manifest} ({len(rows)} rollouts)")
PY

echo
echo "[eval] done. Videos + .json sidecars in $OUTDIR/  (manifest: $MANIFEST)"
echo "[eval] eyeball each mp4 first: prompt-following (did it go to the named slot?)"
echo "       + first-try grasp; note pass/fail in the ground_truth column."
echo "[eval] then auto-score with Robometer (validates it against your eyeballing):"
echo "  ee/robometer/.venv/bin/python ee/assess_robometer.py --manifest $MANIFEST"
