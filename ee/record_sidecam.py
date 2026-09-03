#!/usr/bin/env python3
"""
Record the SIDE camera (clean — no UI overlay dots) from the running vla_server into an
mp4, for the presentation. The server's /observe frames are raw JPEGs; the green trail
dots are a browser-only overlay, so this capture is clean.

Run on the WS WHILE a placement is executing (or anytime — it grabs the live buffer):
    .venv/bin/python ee/record_sidecam.py --server http://192.168.123.198:8000
    # stop with Ctrl+C, or give a fixed length:
    .venv/bin/python ee/record_sidecam.py --duration 25 --out ee/presentation/place_good.mp4

Only NEW frames are written (the server buffers ~10 fps during motion), so the clip
plays at real speed.
"""

import argparse
import base64
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np


def fetch_side(server: str, cam: str):
    with urllib.request.urlopen(f"{server}/observe", timeout=5) as r:
        import json
        imgs = json.loads(r.read()).get("images", {})
    b64 = imgs.get(cam) or imgs.get(cam.replace("cam_", "")) or imgs.get("side")
    if not b64:
        return None, None
    arr = np.frombuffer(base64.b64decode(b64), dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR), b64


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://192.168.123.198:8000")
    ap.add_argument("--cam", default="cam_side")
    ap.add_argument("--out", default=None, help="output mp4 (default ee/presentation/side_<ts>.mp4)")
    ap.add_argument("--fps", type=int, default=10, help="output video fps (server buffers ~10)")
    ap.add_argument("--duration", type=float, default=None, help="seconds to record (default: until Ctrl+C)")
    args = ap.parse_args()

    out = Path(args.out) if args.out else Path(__file__).parent / "presentation" / f"side_{int(time.time())}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)

    writer, last_b64, n = None, None, 0
    t_start = time.perf_counter()
    print(f"Recording {args.cam} from {args.server} -> {out}  (Ctrl+C to stop)")
    try:
        while True:
            if args.duration and time.perf_counter() - t_start >= args.duration:
                break
            frame, b64 = fetch_side(args.server, args.cam)
            if frame is not None and b64 != last_b64:  # only write new frames
                if writer is None:
                    h, w = frame.shape[:2]
                    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"),
                                             args.fps, (w, h))
                writer.write(frame)
                last_b64 = b64
                n += 1
                if n % 10 == 0:
                    print(f"  {n} frames...")
            time.sleep(0.03)  # poll ~30 Hz; dedup keeps only the ~10 unique fps
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        if writer is not None:
            writer.release()
        print(f"Wrote {n} frames -> {out}  ({n / max(time.perf_counter() - t_start, 1e-3):.1f} fps captured)")


if __name__ == "__main__":
    main()
