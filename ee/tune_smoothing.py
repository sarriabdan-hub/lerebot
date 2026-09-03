#!/usr/bin/env python3
"""
Find the smoothing sweet spot from a motor trace — offline, no robot needed.

Idea (the "analytics" approach): record ONE raw run (no smoothing, --smooth-alpha 1.0)
with --trace-motors, then simulate every EMA alpha on the recorded command stream and
measure, per alpha:
  - residual JITTER  = std of step-to-step command deltas (lower = smoother)
  - tracking LAG     = how far the smoothed signal trails the raw motion (higher = laggier)
We then pick the alpha at the "knee": the smallest alpha (smoothest) whose lag is still
under a sensible bound, separately for the body joints and the gripper.

Usage (on the WS, after scp-ing the raw trace):
    .venv/bin/python ee/tune_smoothing.py --csv ee/motor_trace_raw.csv
    .venv/bin/python ee/tune_smoothing.py --csv ee/motor_trace_raw.csv --fps 24 --max-lag-ms 150
"""

import argparse
import numpy as np
import pandas as pd

BODY = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]
ALPHAS = [1.0, 0.8, 0.7, 0.6, 0.5, 0.4, 0.35, 0.3, 0.25, 0.2, 0.15]


def ema(x: np.ndarray, alpha: float) -> np.ndarray:
    y = np.empty_like(x)
    y[0] = x[0]
    for i in range(1, len(x)):
        y[i] = alpha * x[i] + (1 - alpha) * y[i - 1]
    return y


def jitter(x: np.ndarray) -> float:
    """High-frequency content = std of consecutive differences."""
    return float(np.std(np.diff(x))) if len(x) > 1 else 0.0


def tracking_lag(raw: np.ndarray, sm: np.ndarray) -> float:
    """RMS deviation between smoothed and raw — proxy for lag/distortion (same units as signal)."""
    return float(np.sqrt(np.mean((sm - raw) ** 2)))


def col(df, prefix, joint):
    for c in df.columns:
        if c.startswith(prefix) and joint in c:
            return df[c].to_numpy(dtype=float)
    return None


class OneEuro:
    """Same 1-Euro as the server, for offline simulation on a recorded stream."""
    def __init__(self, freq, min_cutoff, beta, d_cutoff=1.0):
        self.freq, self.mc, self.beta, self.dc = freq, min_cutoff, beta, d_cutoff
        self.x = self.dx = self.xp = None
    def _a(self, cutoff):
        import math
        tau = 1.0 / (2 * math.pi * cutoff); te = 1.0 / self.freq
        return 1.0 / (1.0 + tau / te)
    def run(self, xs):
        out = np.empty_like(xs)
        for i, x in enumerate(xs):
            dx = 0.0 if self.xp is None else (x - self.xp) * self.freq
            ad = self._a(self.dc)
            self.dx = dx if self.dx is None else ad * dx + (1 - ad) * self.dx
            a = self._a(self.mc + self.beta * abs(self.dx))
            self.x = x if self.x is None else a * x + (1 - a) * self.x
            self.xp = x
            out[i] = self.x
        return out


def rest_motion_masks(x, fps):
    """Split samples into 'rest/slow' vs 'fast' by per-step speed (deg/s) median split."""
    v = np.abs(np.diff(x)) * fps
    v = np.append(v, v[-1])
    thr = np.median(v) * 1.5
    return v <= thr, v > thr  # (rest_mask, motion_mask)


def sweep_oneeuro(df, fps):
    print("\n=== 1-EURO SWEEP (offline) — rest-jitter (want low) vs motion-lag (want low) ===")
    MCS = [2.0, 1.0, 0.7, 0.5, 0.3]      # min_cutoff: lower = smoother at rest
    BETAS = [0.0, 0.02, 0.05, 0.1, 0.3, 1.0]  # beta: higher = less lag when fast
    best = None
    print(f"{'min_cut':>7} {'beta':>6} {'rest_jit':>9} {'motion_lag':>11}   score")
    for mc in MCS:
        for beta in BETAS:
            rj, ml = [], []
            for j in BODY:
                x = col(df, "cmd.", j)
                if x is None:
                    continue
                y = OneEuro(fps, mc, beta).run(x)
                rest, motion = rest_motion_masks(x, fps)
                rj.append(np.std(np.diff(y)[rest[:-1]]) if rest[:-1].any() else 0.0)
                ml.append(np.sqrt(np.mean((y - x)[motion] ** 2)) if motion.any() else 0.0)
            rjm, mlm = float(np.mean(rj)), float(np.mean(ml))
            score = rjm + 0.5 * mlm  # weight jitter a bit more than lag
            if best is None or score < best[0]:
                best = (score, mc, beta, rjm, mlm)
            print(f"{mc:>7.1f} {beta:>6.2f} {rjm:>9.3f} {mlm:>11.3f}   {score:.3f}")
    print("\n" + "=" * 56)
    print("RECOMMENDED 1-EURO (set in the UI live-tune card):")
    print(f"  filter          oneeuro")
    print(f"  euro min_cutoff {best[1]}")   # best = (score, mc, beta, rj, ml)
    print(f"  euro beta       {best[2]}")
    print(f"  (rest jitter {best[3]:.3f} deg/step, motion lag {best[4]:.3f} deg)")
    print("  NOTE: if raw jitter is huge, this metric conflates jitter with motion and")
    print("        under-smooths — prefer LIVE tuning. Good start: min_cutoff 0.5, beta 0.1.")
    print("=" * 56)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="motor_trace.csv (ideally a RAW alpha=1.0 run)")
    ap.add_argument("--fps", type=float, default=24.0, help="control rate (for lag in ms)")
    ap.add_argument("--max-lag-ms", type=float, default=150.0, help="acceptable tracking lag budget")
    ap.add_argument("--jitter-target", type=float, default=0.25,
                    help="fraction of raw jitter to accept (0.25 = cut jitter to 25%%)")
    ap.add_argument("--mode", default="both", choices=["ema", "oneeuro", "both"],
                    help="which filter to analyze (default both)")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    dt_ms = 1000.0 / args.fps

    if args.mode in ("oneeuro", "both"):
        sweep_oneeuro(df, args.fps)
    if args.mode == "oneeuro":
        return

    # ---- body joints: average jitter/lag across the 5 joints ----
    print(f"\n=== BODY JOINTS (cmd.*) — {len(df)} steps @ {args.fps} Hz ===")
    raw_j = {j: jitter(col(df, "cmd.", j)) for j in BODY if col(df, "cmd.", j) is not None}
    print("raw step-to-step jitter (deg):  " + "  ".join(f"{j.split('_')[0]}={v:.2f}" for j, v in raw_j.items()))
    raw_body = np.mean(list(raw_j.values()))
    print(f"raw body jitter (mean): {raw_body:.3f} deg/step\n")

    print(f"{'alpha':>6} {'jitter':>8} {'%raw':>6} {'lag_ms':>7}   verdict")
    body_pick = None
    for a in ALPHAS:
        js, lags = [], []
        for j in BODY:
            x = col(df, "cmd.", j)
            if x is None:
                continue
            y = ema(x, a)
            js.append(jitter(y))
            lags.append(tracking_lag(x, y))
        jm, lagm = np.mean(js), np.mean(lags)
        lag_ms = (1 - a) / a * dt_ms if a > 0 else 9e9   # EMA group delay ~ (1-a)/a samples
        ok_j = jm <= args.jitter_target * raw_body
        ok_l = lag_ms <= args.max_lag_ms
        verdict = "  <-- candidate" if (ok_j and ok_l) else ("jitter ok, laggy" if ok_j else "")
        if ok_j and ok_l and body_pick is None:
            body_pick = a
        print(f"{a:>6.2f} {jm:>8.3f} {100*jm/max(raw_body,1e-9):>5.0f}% {lag_ms:>7.0f}   {verdict}")

    # ---- gripper ----
    g = col(df, "cmd.", "gripper")
    print("\n=== GRIPPER (cmd.gripper) ===")
    grip_pick = None
    if g is not None:
        raw_g = jitter(g)
        print(f"raw gripper jitter: {raw_g:.3f}/step  (range {g.min():.1f}..{g.max():.1f})\n")
        print(f"{'alpha':>6} {'jitter':>8} {'%raw':>6} {'lag_ms':>7}")
        for a in ALPHAS:
            y = ema(g, a)
            jg = jitter(y)
            lag_ms = (1 - a) / a * dt_ms if a > 0 else 9e9
            mark = "  <-- candidate" if (jg <= args.jitter_target * raw_g and lag_ms <= args.max_lag_ms) else ""
            if mark and grip_pick is None:
                grip_pick = a
            print(f"{a:>6.2f} {jg:>8.3f} {100*jg/max(raw_g,1e-9):>5.0f}% {lag_ms:>7.0f}{mark}")
    else:
        print("no cmd.gripper column found")

    print("\n" + "=" * 56)
    print("RECOMMENDATION (set via the UI live-tune card):")
    print(f"  --smooth-alpha  {body_pick if body_pick else 0.3}")
    print(f"  --gripper-alpha {grip_pick if grip_pick else 0.5}")
    print("  (smooth-alpha = smallest alpha that cuts body jitter to target AND keeps lag<budget)")
    print("=" * 56)


if __name__ == "__main__":
    main()
