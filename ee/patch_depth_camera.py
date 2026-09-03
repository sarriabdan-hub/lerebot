#!/usr/bin/env python3
"""Make the SO-101 follower actually RECORD the RealSense depth stream.

WHY: setting `"use_depth": true` in the camera config is NOT enough. The
RealSense driver captures depth into `latest_depth_frame`, but
SO101Follower.get_observation() only ever reads the COLOUR frame, and
`_cameras_ft` never declares a depth feature -> lerobot-record writes no
depth video and you find out 50 episodes too late.

WHAT THIS DOES (3 hunks, idempotent):
  1. adds colorize_depth(): uint16 mm -> 3-channel RGB with a FIXED mapping
     (clip 0.25-1.20 m, JET, invalid pixels -> black). Fixed on purpose: a
     per-frame autoscale would make the same colour mean a different distance
     in every frame, destroying the pixel<->depth correspondence the policy
     needs to learn (and the inference-time colouring must use these SAME
     constants -- see ee/DEPTH_PLAN.md).
  2. _cameras_ft: declares "cam_depth" (H, W, 3) so the dataset creates the
     stream.
  3. get_observation: emits obs_dict["cam_depth"] from the already-captured
     latest_depth_frame (non-blocking; the driver's background thread fills it).

Result: the recording gains `observation.images.cam_depth` -- just another RGB
video stream, so pi0.5/GR00T consume it with zero architecture change, and it
can be A/B'd by simply not passing the key at train time.

Run ON THOR (path is Thor's lerobot source):
    python patch_depth_camera.py \
      /home/robot/dev/lerebot/lerobot/src/lerobot/robots/so_follower/so_follower.py
Then re-run the depth trial recording.
"""

import shutil
import sys
from pathlib import Path

HELPER = '''

# ── depth -> colorized RGB (patch_depth_camera.py) ───────────────────────────
# FIXED mapping. Do NOT autoscale per frame: the same colour must always mean
# the same distance, at record time AND at inference time.
DEPTH_NEAR_M = 0.25
DEPTH_FAR_M = 1.20


def colorize_depth(depth_mm):
    """RealSense z16 depth (uint16 millimetres) -> HxWx3 uint8 RGB."""
    import cv2
    import numpy as np

    d = depth_mm.astype(np.float32) / 1000.0
    u8 = ((np.clip(d, DEPTH_NEAR_M, DEPTH_FAR_M) - DEPTH_NEAR_M)
          / (DEPTH_FAR_M - DEPTH_NEAR_M) * 255.0).astype(np.uint8)
    bgr = cv2.applyColorMap(u8, cv2.COLORMAP_JET)
    rgb = bgr[..., ::-1].copy()                 # BGR -> RGB
    # Invalid pixels (0 = no return) MUST be forced to pure black AFTER the
    # colormap: JET(0) is dark red, identical to the NEAREST distance. The
    # RealSense returns 0 on transparent/shiny surfaces — i.e. on the glass
    # vials themselves — so without this, "cannot measure" would be encoded as
    # "right at the gripper".
    rgb[depth_mm == 0] = 0
    return rgb
# ─────────────────────────────────────────────────────────────────────────────
'''

FT_OLD = '''    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return {
            cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3) for cam in self.cameras
        }'''

FT_NEW = '''    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        ft = {
            cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3) for cam in self.cameras
        }
        # patch_depth_camera.py: declare the colorized depth stream so the
        # dataset actually creates observation.images.cam_depth
        for cam in self.cameras:
            if getattr(self.config.cameras[cam], "use_depth", False):
                ft["cam_depth"] = (
                    self.config.cameras[cam].height,
                    self.config.cameras[cam].width,
                    3,
                )
        return ft'''

OBS_OLD = '''        # Capture images from cameras
        for cam_key, cam in self.cameras.items():
            start = time.perf_counter()
            obs_dict[cam_key] = cam.read_latest()
            dt_ms = (time.perf_counter() - start) * 1e3
            logger.debug(f"{self} read {cam_key}: {dt_ms:.1f}ms")

        return obs_dict'''

OBS_NEW = '''        # Capture images from cameras
        for cam_key, cam in self.cameras.items():
            start = time.perf_counter()
            obs_dict[cam_key] = cam.read_latest()
            dt_ms = (time.perf_counter() - start) * 1e3
            logger.debug(f"{self} read {cam_key}: {dt_ms:.1f}ms")

        # patch_depth_camera.py: emit the colorized depth frame. Uses the frame
        # the driver's background thread already captured (non-blocking), so the
        # 30 Hz record loop is not slowed by a synchronous depth read.
        for cam in self.cameras.values():
            if getattr(cam, "use_depth", False):
                raw_depth = getattr(cam, "latest_depth_frame", None)
                if raw_depth is not None:
                    obs_dict["cam_depth"] = colorize_depth(raw_depth)
                break

        return obs_dict'''


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"ERROR: no such file: {path}")
        return 1
    src = path.read_text()

    if "colorize_depth" in src:
        print(f"already patched: {path}")
        return 0

    problems = []
    if FT_OLD not in src:
        problems.append("_cameras_ft block did not match")
    if OBS_OLD not in src:
        problems.append("get_observation camera loop did not match")
    if problems:
        print("ERROR: " + "; ".join(problems))
        print("This lerobot version differs. Apply the 3 hunks by hand — see")
        print("ee/DEPTH_PLAN.md section 'Thor patch'.")
        return 1

    # 1) helper after the imports (before the first class definition)
    anchor = "\nclass "
    i = src.index(anchor)
    src = src[:i] + HELPER + src[i:]
    # 2) + 3)
    src = src.replace(FT_OLD, FT_NEW, 1)
    src = src.replace(OBS_OLD, OBS_NEW, 1)

    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    path.write_text(src)
    print(f"PATCHED {path}")
    print(f"backup  {backup}")
    print("\nVerify:  grep -n colorize_depth", path)
    print("Then record — videos/ must contain observation.images.cam_depth")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
