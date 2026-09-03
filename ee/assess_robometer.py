#!/usr/bin/env python3
"""
Batch success/progress scoring of our recorded runs with Robometer (arXiv 2603.02115).

Loads Robometer-4B ONCE, then scores many videos: per-frame progress curve + success
probability + verdict. Three input modes:

  1) Single video:
       python ee/assess_robometer.py --video ee/presentation/exec_cam_side_XXX.mp4 \
           --task "Place the red vial in position 1 of the left rack."
  2) Manifest (validation pilot — videos with KNOWN outcomes):
       python ee/assess_robometer.py --manifest ee/robometer_pilot.csv
       # CSV columns: video,task[,ground_truth]   (ground_truth: 1=success 0=fail)
  3) LeRobot dataset (score every episode video, task read from metadata):
       python ee/assess_robometer.py --lerobot-root ./data/vial-sort-v4-merged-ee --cam cam_side

Output: one JSON line per video -> --out (default ee/robometer_scores.jsonl) with
{video, task, success_prob, verdict, progress_first/last/max, stalled, ground_truth?}.
If ground_truth present: prints accuracy / agreement summary at the end (the >=85% gate
from PLAN_FABLE 4b).

SETUP (separate env — robometer pins its own deps, do NOT install into lerobot's venv):
    cd ee/robometer && uv sync          # creates ee/robometer/.venv
    cd ../.. && ee/robometer/.venv/bin/python ee/assess_robometer.py ...
First run downloads robometer/Robometer-4B from HF (~8GB). GPU strongly recommended.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

# make the cloned repo importable when running from lerobot root
sys.path.insert(0, str(Path(__file__).parent / "robometer"))

import torch  # noqa: E402
from robometer.data.dataset_types import ProgressSample, Trajectory  # noqa: E402
from robometer.evals.eval_server import compute_batch_outputs  # noqa: E402
from robometer.evals.eval_viz_utils import extract_frames  # noqa: E402
from robometer.utils.save import load_model_from_hf  # noqa: E402
from robometer.utils.setup_utils import setup_batch_collator  # noqa: E402

DEFAULT_MODEL = "robometer/Robometer-4B"


class RobometerScorer:
    """Load once, score many. Mirrors scripts/example_inference_local.py exactly."""

    def __init__(self, model_path: str = DEFAULT_MODEL, device: str | None = None):
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        print(f"loading {model_path} on {self.device} (first run downloads ~8GB)...")
        # Force the STANDARD (plain-transformers) loader, not unsloth's. The checkpoint config sets
        # use_unsloth=True (it was trained with unsloth), but unsloth's FastVisionModel mis-loads the
        # vision tower for EVAL — it leaves the visual in fp32 ("Before and after visual are the same"
        # warning) and produces wrong/near-zero success (e.g. the SOAR example clip). load_model_from_hf
        # re-imports setup_model_and_processor at call time, so patching the module attr here takes
        # effect; we just flip use_unsloth off on the model config before the model is built.
        import robometer.utils.setup_utils as _su
        if not getattr(_su, "_rbm_no_unsloth_patched", False):
            _orig_smp = _su.setup_model_and_processor
            def _smp_no_unsloth(model_cfg, *a, **k):
                try:
                    model_cfg.use_unsloth = False
                except Exception:  # noqa: BLE001
                    pass
                return _orig_smp(model_cfg, *a, **k)
            _su.setup_model_and_processor = _smp_no_unsloth
            _su._rbm_no_unsloth_patched = True
        self.exp_config, self.tokenizer, self.processor, self.model = load_model_from_hf(
            model_path=model_path, device=self.device)
        self.model.eval()
        # Belt-and-suspenders: ensure a single dtype so the vision LayerNorm can't hit
        # "expected scalar type BFloat16 but found Float" (no-op if already uniform bf16).
        self.model = self.model.to(torch.bfloat16)
        self.collator = setup_batch_collator(self.processor, self.tokenizer, self.exp_config, is_eval=True)
        loss_cfg = getattr(self.exp_config, "loss", None)
        self.is_discrete = (getattr(loss_cfg, "progress_loss_type", "l2").lower() == "discrete"
                            if loss_cfg else False)
        self.num_bins = (getattr(loss_cfg, "progress_discrete_bins", None)
                         or getattr(self.exp_config.model, "progress_discrete_bins", 10))

    @torch.inference_mode()
    def score(self, frames: np.ndarray, task: str) -> dict:
        T = int(frames.shape[0])
        traj = Trajectory(frames=frames, frames_shape=tuple(frames.shape), task=task, id="0",
                          metadata={"subsequence_length": T}, video_embeddings=None)
        batch = self.collator([ProgressSample(trajectory=traj, sample_type="progress")])
        inputs = batch["progress_inputs"]
        # the model is bf16 but the processor emits float32 pixel_values; cast float inputs to the
        # model dtype (ints like input_ids / image_grid_thw stay as-is) or the vision tower errors
        # with "expected scalar type BFloat16 but found Float".
        mdtype = next(self.model.parameters()).dtype
        for k, v in inputs.items():
            if hasattr(v, "to"):
                inputs[k] = v.to(self.device, dtype=mdtype) if torch.is_floating_point(v) else v.to(self.device)
        results = compute_batch_outputs(self.model, self.tokenizer, inputs, sample_type="progress",
                                        is_discrete_mode=self.is_discrete, num_bins=self.num_bins)
        prog = results.get("progress_pred", [[]])
        prog = np.array(prog[0], dtype=np.float32) if prog and len(prog) else np.array([])
        succ = (results.get("outputs_success") or {}).get("success_probs", [])
        succ = np.array(succ[0], dtype=np.float32) if succ and len(succ) else np.array([])
        # success at the frame where progress peaks: for full episodes that end with the arm
        # retreating home, the last frame is NOT the completion moment, so succ[-1] under-reads.
        succ_at_peak = None
        if succ.size and prog.size and succ.size == prog.size:
            succ_at_peak = round(float(succ[int(np.argmax(prog))]), 3)
        return {
            "progress": prog.tolist(),
            "success": succ.tolist(),
            "progress_first": round(float(prog[0]), 3) if prog.size else None,
            "progress_last": round(float(prog[-1]), 3) if prog.size else None,
            "progress_max": round(float(prog.max()), 3) if prog.size else None,
            # stall heuristic (paper's failure-detection idea): peaked then fell back >0.2
            "stalled": bool(prog.size and (prog.max() - prog[-1]) > 0.2),
            "success_prob": round(float(succ[-1]), 3) if succ.size else None,
            "success_max": round(float(succ.max()), 3) if succ.size else None,
            "success_at_progpeak": succ_at_peak,
        }


def load_video_frames(path: str, fps: float, max_frames: int) -> np.ndarray:
    frames = extract_frames(path, fps=fps, max_frames=max_frames)
    if frames is None or frames.size == 0:
        raise RuntimeError(f"no frames from {path}")
    if frames.dtype != np.uint8:
        frames = np.clip(frames, 0, 255).astype(np.uint8)
    return frames


def iter_lerobot_episodes(root: Path, cam: str):
    """Yield (video_path, task, episode_index) for a v2.x or v3 lerobot dataset."""
    meta = root / "meta" / "episodes.jsonl"
    tasks = {}
    if meta.exists():
        for line in meta.read_text().splitlines():
            d = json.loads(line)
            t = d.get("tasks") or [d.get("task", "?")]
            tasks[d["episode_index"]] = t[0]
    else:
        import pandas as pd
        for f in sorted((root / "meta" / "episodes").rglob("*.parquet")):
            df = pd.read_parquet(f)
            tcol = "tasks" if "tasks" in df.columns else "task"
            for _, row in df.iterrows():
                t = row[tcol]
                tasks[int(row["episode_index"])] = t if isinstance(t, str) else list(t)[0]
    vids = sorted(root.rglob(f"*{cam}*/*.mp4")) or sorted(root.rglob(f"*{cam}*.mp4"))
    for v in vids:
        stem = v.stem  # episode_000042 or file-000
        digits = "".join(ch for ch in stem if ch.isdigit())
        ep = int(digits) if digits else -1
        if ep in tasks:
            yield str(v), tasks[ep], ep


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--video", help="single video path")
    src.add_argument("--manifest", help="CSV: video,task[,ground_truth]")
    src.add_argument("--lerobot-root", help="lerobot dataset root — scores every episode video")
    ap.add_argument("--task", help="instruction (required with --video)")
    ap.add_argument("--cam", default="cam_side", help="camera for --lerobot-root (default cam_side)")
    ap.add_argument("--model-path", default=DEFAULT_MODEL)
    ap.add_argument("--fps", type=float, default=1.0, help="frame-sampling fps (default 1.0)")
    ap.add_argument("--max-frames", type=int, default=64)
    ap.add_argument("--threshold", type=float, default=0.5, help="success_prob verdict threshold")
    ap.add_argument("--limit", type=int, default=None, help="score at most N videos")
    ap.add_argument("--out", default="ee/robometer_scores.jsonl")
    args = ap.parse_args()

    jobs = []  # (video, task, ground_truth|None)
    if args.video:
        if not args.task:
            ap.error("--task is required with --video")
        jobs = [(args.video, args.task, None)]
    elif args.manifest:
        with open(args.manifest) as fh:
            for row in csv.DictReader(fh):
                gt = row.get("ground_truth")
                jobs.append((row["video"], row["task"], int(gt) if gt not in (None, "") else None))
    else:
        jobs = [(v, t, None) for v, t, _ in iter_lerobot_episodes(Path(args.lerobot_root), args.cam)]
    if args.limit:
        jobs = jobs[: args.limit]
    if not jobs:
        raise SystemExit("no videos to score")
    print(f"{len(jobs)} videos to score -> {args.out}")

    scorer = RobometerScorer(args.model_path)
    n_ok = n_gt = n_agree = 0
    with open(args.out, "a") as out:
        for i, (video, task, gt) in enumerate(jobs):
            try:
                frames = load_video_frames(video, args.fps, args.max_frames)
                r = scorer.score(frames, task)
            except Exception as e:  # noqa: BLE001
                print(f"[{i+1}/{len(jobs)}] ERROR {video}: {e!r}")
                continue
            verdict = int((r["success_prob"] or 0.0) >= args.threshold)
            rec = {"video": video, "task": task, "verdict": verdict, **r, "ts": round(time.time(), 1)}
            if gt is not None:
                rec["ground_truth"] = gt
                n_gt += 1
                n_agree += int(verdict == gt)
            out.write(json.dumps(rec) + "\n")
            out.flush()
            n_ok += 1
            print(f"[{i+1}/{len(jobs)}] succ={r['success_prob']} last_prog={r['progress_last']} "
                  f"stalled={r['stalled']} verdict={verdict}"
                  + (f" gt={gt} {'OK' if verdict == gt else 'MISS'}" if gt is not None else "")
                  + f"  {Path(video).name}")

    print(f"\nscored {n_ok}/{len(jobs)} -> {args.out}")
    if n_gt:
        print(f"AGREEMENT vs ground truth: {n_agree}/{n_gt} = {100*n_agree/n_gt:.0f}%  "
              f"(PLAN_FABLE gate: >=85% to adopt as the success judge)")


if __name__ == "__main__":
    main()
