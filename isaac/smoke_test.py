"""
Smoke test: build the scene, set a sheet episode's vial layout, wave the arm,
and dump one PNG per camera to isaac/out/ so you can tune camera poses against
the real reference frames (ee/extract_ref_frame.py output).

Run (inside the isaac env):
    python isaac/smoke_test.py --headless          # offscreen render
    python isaac/smoke_test.py                     # with the GUI
"""

import argparse
import math
import os
import sys
from pathlib import Path

# /tmp/isaaclab may be owned by another user; isaaclab logs via tempfile.gettempdir()
_tmp = Path.home() / ".cache" / "isaaclab-tmp"
_tmp.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("TMPDIR", str(_tmp))

sys.path.insert(0, str(Path(__file__).parent))

from isaaclab.app import AppLauncher  # noqa: E402  (must run before other isaaclab imports)

parser = argparse.ArgumentParser()
parser.add_argument("--episode", type=int, default=3, help="sheet episode to stage")
parser.add_argument("--seconds", type=float, default=4.0, help="how long to wave the arm")
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
args.enable_cameras = True
app = AppLauncher(args).app

# isaaclab-dependent imports only AFTER the app exists
import numpy as np  # noqa: E402
from isaaclab.sim import SimulationCfg, SimulationContext  # noqa: E402

import sim_config as C  # noqa: E402
from scene import VialSortScene  # noqa: E402
from sheet import parse_sheet  # noqa: E402


def main():
    sim = SimulationContext(SimulationCfg(dt=C.PHYSICS_DT, device="cuda:0"))
    scene = VialSortScene(sim)
    sim.reset()
    scene.initialize()

    eps = parse_sheet(C.SHEET_PATH)
    ep = eps[args.episode]
    print(f"staging ep {ep.index}: {ep.task!r}  -> {ep.dest}")
    scene.set_scene(ep)

    home = {f"{j}.pos": v for j, v in C.HOME_POSE_DEG.items()}
    n = int(args.seconds * C.FPS)
    for i in range(n):
        # small sinusoidal wave around home to prove drives + wrist cam track
        act = dict(home)
        act["shoulder_pan.pos"] = home["shoulder_pan.pos"] + 20 * math.sin(2 * math.pi * i / n)
        act["gripper.pos"] = 50 + 50 * math.sin(4 * math.pi * i / n)
        scene.set_joint_targets(act)
        scene.step()

    out_dir = Path(__file__).parent / "out"
    out_dir.mkdir(exist_ok=True)
    try:
        from PIL import Image
        for name, img in scene.get_images().items():
            Image.fromarray(img).save(out_dir / f"{name}.png")
            print(f"wrote {out_dir / f'{name}.png'}  {img.shape} mean={img.mean():.1f}")
    except ImportError:
        for name, img in scene.get_images().items():
            np.save(out_dir / f"{name}.npy", img)
            print(f"PIL missing; wrote {name}.npy  {img.shape} mean={img.mean():.1f}")

    print("joint state:", {k: round(v, 1) for k, v in scene.get_joint_state().items()})
    app.close()


if __name__ == "__main__":
    main()
