#!/usr/bin/env python3
"""
Convert a LeRobot dataset -> Cosmos Policy (ALOHA-style) per-episode HDF5 + MP4s.

Cosmos Policy post-training (github.com/nvidia/cosmos + cosmos-cookbook) consumes an
ALOHA-style layout, modeled on nvidia/ALOHA-Cosmos-Policy: one HDF5 per episode with
  /observations/qpos   (T, D)   proprioceptive state
  /observations/qvel   (T, D)   finite-difference velocity
  /observations/effort (T, D)   torques (zeros here; SO-101 has none)
  /observations/video_paths/<cam>   attr -> relative mp4 path
  /action              (T, D)   absolute action
  /relative_action     (T, D)   frame-to-frame delta
plus one MP4 per camera view. Actions/state are stored RAW; normalization to [-1,1]
happens in Cosmos training from dataset stats (we also emit norm_stats.json). Task
text is stored externally (tasks.json) and as an HDF5 root attr.

Output:
  OUT/
    episode_000.hdf5 ...
    videos/episode_000/<cam>.mp4
    tasks.json          {ep: task}
    norm_stats.json     per-dim min/max/mean/std for state & action
    dataset_info.json   dims / cameras / resolution / fps / episodes

ALIGN WITH THE COSMOS CONFIG (cosmos_policy/config/config.py) after converting:
  - our robot is single-arm -> state_dim = action_dim = 7 (EE: x,y,z,wx,wy,wz,grip),
    NOT ALOHA's 14. Set the config's state/action dims to match dataset_info.json.
  - camera keys/count (top, wrist, side), image resolution (default 256), fps.

Run (validate on 2 episodes first, then full):
  .venv/bin/python ee/cosmos_convert.py --root ./data/vial-sort-v5-ee-rgb \
      --repo-id sari-abdan/vial-sort-v5-ee-rgb --out ./data/vial-sort-v5-cosmos --limit 2
  .venv/bin/python ee/cosmos_convert.py --root ./data/vial-sort-v5-ee-rgb \
      --repo-id sari-abdan/vial-sort-v5-ee-rgb --out ./data/vial-sort-v5-cosmos
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from lerobot.datasets.lerobot_dataset import LeRobotDataset  # noqa: E402


def _np(x):
    try:
        import torch
        if isinstance(x, torch.Tensor):
            return x.detach().cpu().numpy()
    except Exception:
        pass
    return np.asarray(x)


def _img_rgb_u8(t):
    """LeRobot image (CHW float[0,1] or HWC uint8) -> HWC RGB uint8."""
    a = _np(t)
    if np.issubdtype(a.dtype, np.floating):
        a = (np.clip(a, 0.0, 1.0) * 255.0).astype(np.uint8)
    else:
        a = a.astype(np.uint8)
    if a.ndim == 3 and a.shape[0] in (1, 3) and a.shape[-1] not in (1, 3):
        a = np.transpose(a, (1, 2, 0))          # CHW -> HWC
    if a.shape[-1] == 1:
        a = np.repeat(a, 3, axis=-1)
    return np.ascontiguousarray(a)


def _ffmpeg(path, w, h, fps):
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-an",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(path)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def camera_keys(meta):
    ck = getattr(meta, "camera_keys", None)
    if ck:
        return list(ck)
    return [k for k in meta.features if k.startswith("observation.images")]


def episode_bounds(ds):
    """Return dict ep -> (from, to). Robust across lerobot versions."""
    edi = getattr(ds, "episode_data_index", None)
    if edi is not None and "from" in edi and "to" in edi:
        return {ep: (int(edi["from"][ep]), int(edi["to"][ep]))
                for ep in range(ds.meta.total_episodes)}
    # fallback: scan the episode_index column
    ep_col = np.asarray(_np(ds.hf_dataset["episode_index"]))
    out = {}
    for ep in range(ds.meta.total_episodes):
        idx = np.nonzero(ep_col == ep)[0]
        out[ep] = (int(idx[0]), int(idx[-1]) + 1)
    return out


def get_task(fr, ds, ep):
    t = fr.get("task")
    if isinstance(t, str) and t:
        return t
    try:
        t = ds.meta.episodes[ep]["tasks"]
        return t[0] if isinstance(t, list) else t
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-id", default="sari-abdan/vial-sort-v5-ee-rgb")
    ap.add_argument("--root", default="./data/vial-sort-v5-ee-rgb")
    ap.add_argument("--out", default="./data/vial-sort-v5-cosmos")
    ap.add_argument("--resolution", type=int, default=256, help="square resize; 0 = native")
    ap.add_argument("--fps", type=int, default=0, help="0 = dataset fps")
    ap.add_argument("--limit", type=int, default=0, help="only first N episodes (0=all)")
    args = ap.parse_args()

    import cv2
    import h5py

    ds = LeRobotDataset(args.repo_id, root=args.root)
    fps = args.fps or int(ds.meta.fps)
    cam_keys = camera_keys(ds.meta)
    cam_names = [k.split(".")[-1] for k in cam_keys]
    n_ep = min(ds.meta.total_episodes, args.limit) if args.limit else ds.meta.total_episodes
    bounds = episode_bounds(ds)

    out = Path(args.out)
    (out / "videos").mkdir(parents=True, exist_ok=True)
    print(f"cameras={cam_names}  fps={fps}  res={args.resolution or 'native'}  episodes={n_ep}")

    tasks, all_state, all_action = {}, [], []
    for ep in range(n_ep):
        i0, i1 = bounds[ep]
        vdir = out / "videos" / f"episode_{ep:03d}"
        vdir.mkdir(parents=True, exist_ok=True)

        s0 = _img_rgb_u8(ds[i0][cam_keys[0]])
        H = W = args.resolution if args.resolution else None
        if not args.resolution:
            H, W = s0.shape[0], s0.shape[1]
        writers = {nm: _ffmpeg(vdir / f"{nm}.mp4", W, H, fps) for nm in cam_names}

        qpos, act, task = [], [], None
        for i in range(i0, i1):
            fr = ds[i]
            for key, nm in zip(cam_keys, cam_names):
                img = _img_rgb_u8(fr[key])
                if args.resolution and (img.shape[0] != H or img.shape[1] != W):
                    img = cv2.resize(img, (W, H))
                writers[nm].stdin.write(img.tobytes())
            qpos.append(_np(fr["observation.state"]).astype(np.float32))
            act.append(_np(fr["action"]).astype(np.float32))
            if task is None:
                task = get_task(fr, ds, ep)
        for w in writers.values():
            w.stdin.close()
            w.wait()

        qpos = np.stack(qpos)
        act = np.stack(act)
        rel = np.zeros_like(act); rel[1:] = np.diff(act, axis=0)
        qvel = np.zeros_like(qpos); qvel[1:] = np.diff(qpos, axis=0) * fps
        effort = np.zeros_like(qpos)
        tasks[ep] = task or ""
        all_state.append(qpos); all_action.append(act)

        with h5py.File(out / f"episode_{ep:03d}.hdf5", "w") as f:
            f.attrs["task"] = tasks[ep]
            f.attrs["fps"] = fps
            o = f.create_group("observations")
            o.create_dataset("qpos", data=qpos)
            o.create_dataset("qvel", data=qvel)
            o.create_dataset("effort", data=effort)
            vp = o.create_group("video_paths")
            for nm in cam_names:
                vp.attrs[nm] = f"videos/episode_{ep:03d}/{nm}.mp4"
            f.create_dataset("action", data=act)
            f.create_dataset("relative_action", data=rel)
        print(f"  episode_{ep:03d}: T={len(qpos)} dim={qpos.shape[1]} -> hdf5 + {len(cam_names)} mp4")

    S = np.concatenate(all_state); A = np.concatenate(all_action)

    def stats(x):
        return {"min": x.min(0).tolist(), "max": x.max(0).tolist(),
                "mean": x.mean(0).tolist(), "std": (x.std(0) + 1e-8).tolist()}

    (out / "norm_stats.json").write_text(json.dumps({"state": stats(S), "action": stats(A)}, indent=2))
    (out / "tasks.json").write_text(json.dumps(tasks, indent=2))
    (out / "dataset_info.json").write_text(json.dumps({
        "episodes": n_ep,
        "state_dim": int(S.shape[1]),
        "action_dim": int(A.shape[1]),
        "cameras": cam_names,
        "resolution": args.resolution or [int(s0.shape[1]), int(s0.shape[0])],
        "fps": fps,
        "format": "aloha-style hdf5 + per-camera mp4 (Cosmos Policy target)",
    }, indent=2))
    print(f"\nDone: {n_ep} episodes -> {out}")
    print(f"state_dim=action_dim={S.shape[1]} (single-arm EE) -- set this in cosmos_policy config.")


if __name__ == "__main__":
    main()
