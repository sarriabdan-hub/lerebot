#!/usr/bin/env python3
"""
Extract per-episode camera clips from a LeRobot **v3** dataset (where many episodes are
concatenated into each video file) and write a manifest for ee/assess_robometer.py.

v3 packs episodes into `videos/{key}/chunk-XXX/file-YYY.mp4`; the per-episode segment is
given by `.../from_timestamp` and `.../to_timestamp` in meta/episodes/*.parquet, along with
the exact `tasks` string. assess_robometer's --lerobot-root assumes one file == one episode,
which is wrong for v3 — this script fixes that by cutting each episode out with ffmpeg.

Usage:
    python ee/extract_episode_clips.py --root data/vial-sort-v5-ee-rgb --cam cam_side \
        --sample 15 --out-dir ee/episode_clips --manifest ee/demo_manifest.csv
    # then (robometer venv):
    ee/robometer/.venv/bin/python ee/assess_robometer.py --manifest ee/demo_manifest.csv --fps 3

Demos are expert teleop, i.e. successes → the manifest is written with ground_truth=1.
"""
from __future__ import annotations

import argparse
import csv
import glob
import subprocess
from pathlib import Path

import pandas as pd


def load_episodes(root: Path, cam_key: str) -> list[dict]:
    files = sorted(glob.glob(str(root / "meta" / "episodes" / "*" / "*.parquet")))
    if not files:
        raise SystemExit(f"no episodes parquet under {root}/meta/episodes")
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    ck = f"videos/observation.images.{cam_key}"
    need = [f"{ck}/chunk_index", f"{ck}/file_index", f"{ck}/from_timestamp", f"{ck}/to_timestamp"]
    for c in need:
        if c not in df.columns:
            raise SystemExit(f"missing column {c!r}; available cams: "
                             + str([c for c in df.columns if c.startswith('videos/')]))
    out = []
    for _, r in df.iterrows():
        tasks = r["tasks"]
        task = tasks if isinstance(tasks, str) else list(tasks)[0]
        out.append({
            "episode_index": int(r["episode_index"]),
            "task": task,
            "chunk": int(r[f"{ck}/chunk_index"]),
            "file": int(r[f"{ck}/file_index"]),
            "from": float(r[f"{ck}/from_timestamp"]),
            "to": float(r[f"{ck}/to_timestamp"]),
        })
    out.sort(key=lambda e: e["episode_index"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="lerobot v3 dataset root")
    ap.add_argument("--cam", default="cam_side")
    ap.add_argument("--episodes", help="comma-separated episode indices (overrides --sample)")
    ap.add_argument("--sample", type=int, default=15, help="evenly-spaced episodes to take")
    ap.add_argument("--out-dir", default="ee/episode_clips")
    ap.add_argument("--manifest", default="ee/demo_manifest.csv")
    ap.add_argument("--ground-truth", default="1", help="value written to the manifest (demos=1)")
    args = ap.parse_args()

    root = Path(args.root)
    cam_key = args.cam
    eps = load_episodes(root, cam_key)
    by_idx = {e["episode_index"]: e for e in eps}

    if args.episodes:
        pick = [int(x) for x in args.episodes.split(",")]
    else:
        n = min(args.sample, len(eps))
        step = max(len(eps) // n, 1)
        pick = [eps[i]["episode_index"] for i in range(0, len(eps), step)][:n]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    video_tmpl = "videos/observation.images.{key}/chunk-{chunk:03d}/file-{file:03d}.mp4"

    rows = []
    for ep in pick:
        e = by_idx.get(ep)
        if e is None:
            print(f"  ep {ep}: NOT FOUND, skipping")
            continue
        src = root / video_tmpl.format(key=cam_key, chunk=e["chunk"], file=e["file"])
        if not src.exists():
            print(f"  ep {ep}: source missing {src}")
            continue
        dst = out_dir / f"ep{ep:04d}_{cam_key}.mp4"
        # accurate cut: input seeking + re-encode (stream-copy would snap to keyframes)
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(src),
               "-ss", f"{e['from']:.3f}", "-to", f"{e['to']:.3f}",
               "-c:v", "libx264", "-an", str(dst)]
        subprocess.run(cmd, check=True)
        rows.append({"video": str(dst), "task": e["task"], "ground_truth": args.ground_truth})
        print(f"  ep {ep:3d}  [{e['from']:6.2f}-{e['to']:6.2f}s file-{e['file']:03d}]  {e['task'][:60]}")

    with open(args.manifest, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["video", "task", "ground_truth"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nextracted {len(rows)} clips -> {out_dir}\nmanifest -> {args.manifest}")


if __name__ == "__main__":
    main()
