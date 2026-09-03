"""
Sim server — the ONLY script that runs in the isaac-venv (Python 3.11).

lerobot's source needs Python 3.12+, so it cannot run inside Isaac's 3.11
environment. Same split as the real rig (vla_server.py on Thor + WS clients):
this server owns the Isaac scene and steps it continuously at 30 Hz in real
time (like a real robot that keeps existing between commands); teleop_record.py
and eval_pi05.py run in the normal lerobot env and talk to it over HTTP.

Endpoints (JSON):
    GET  /ping    -> {"ok": true, "episodes": N, "fps": 30}
    POST /reset   {"episode": i, "v4": false}   stage sheet/v4 episode + home
                  -> episode info (task, dest, layout)
    POST /home    -> {"ok": true}
    POST /act     {"action": {"shoulder_pan.pos": deg, ..., "gripper.pos": 0..100}}
                  -> {"ok": true}   (targets applied on the next 30 Hz tick)
    GET  /obs     -> {"state": {...}, "images": {"cam_top": <b64 jpeg>, ...}}

Run (isaac-venv):
    source ~/isaac-venv/bin/activate
    python /home/sari/lerobot/isaac/sim_server.py --headless      # or with GUI
"""

import argparse
import base64
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# /tmp/isaaclab may be owned by another user on shared machines; isaaclab's
# logger uses tempfile.gettempdir(), which honors TMPDIR — point it somewhere ours.
_tmp = Path.home() / ".cache" / "isaaclab-tmp"
_tmp.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("TMPDIR", str(_tmp))

sys.path.insert(0, str(Path(__file__).parent))

from isaaclab.app import AppLauncher  # noqa: E402  (before other isaaclab imports)

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=6060)
parser.add_argument("--with-bin", action="store_true",
                    help="add the v5 bin. DEFAULT = NO bin (exact v4 replica scene).")
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
args.enable_cameras = True
app = AppLauncher(args).app

# ── post-app imports ─────────────────────────────────────────────────────────
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from isaaclab.sim import SimulationCfg, SimulationContext  # noqa: E402

import sim_config as C  # noqa: E402
from scene import VialSortScene  # noqa: E402
from sheet import make_v4_episodes, parse_sheet  # noqa: E402

# ── shared state between HTTP threads and the sim main loop ─────────────────
LOCK = threading.Lock()
SHARED = {
    "target": None,        # pending action dict from /act
    "reset": None,         # pending (episode_idx, v4) from /reset
    "teleport": None,      # pending (vial_key, [x,y,z]) debug move
    "home": False,
    "obs": None,           # latest {"state": ..., "images": {...b64 jpeg...}}
    "reset_done": threading.Event(),
    "reset_info": None,
}
EPISODES_V5 = parse_sheet(C.SHEET_PATH)
EPISODES_V4 = make_v4_episodes()


def encode_images(imgs: dict) -> dict:
    out = {}
    for name, rgb in imgs.items():
        ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                               [cv2.IMWRITE_JPEG_QUALITY, 92])
        out[name] = base64.b64encode(buf.tobytes()).decode("ascii")
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence per-request logging
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path == "/ping":
            self._send({"ok": True, "episodes": len(EPISODES_V5),
                        "episodes_v4": len(EPISODES_V4), "fps": C.FPS})
        elif self.path == "/obs":
            with LOCK:
                obs = SHARED["obs"]
            self._send(obs if obs else {"error": "no obs yet"}, 200 if obs else 503)
        elif self.path.startswith("/stream"):
            # MJPEG stream viewable in any browser: /stream?cam=cam_top (default cam_side)
            from urllib.parse import parse_qs, urlparse
            cam = parse_qs(urlparse(self.path).query).get("cam", ["cam_side"])[0]
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while True:
                    with LOCK:
                        obs = SHARED["obs"]
                    b64 = (obs or {}).get("images", {}).get(cam)
                    if b64:
                        jpg = base64.b64decode(b64)
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(jpg)}\r\n\r\n".encode())
                        self.wfile.write(jpg)
                        self.wfile.write(b"\r\n")
                    time.sleep(1.0 / 15)          # 15 fps is plenty for monitoring
            except (BrokenPipeError, ConnectionResetError):
                pass  # viewer closed the tab
        elif self.path in ("/", "/view"):
            # monitoring page for the laptop: all three cams side by side
            html = b"""<!doctype html><title>vial-sort sim</title>
<body style="margin:0;background:#111;color:#eee;font-family:monospace;text-align:center">
<h3 style="margin:8px">vial-sort sim &mdash; cam_top | cam_side | cam_wrist</h3>
<img src="/stream?cam=cam_top"   style="width:33%">
<img src="/stream?cam=cam_side"  style="width:33%">
<img src="/stream?cam=cam_wrist" style="width:33%">
</body>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        else:
            self._send({"error": "unknown path"}, 404)

    def do_POST(self):
        body = self._body()
        if self.path == "/act":
            with LOCK:
                SHARED["target"] = body.get("action", {})
            self._send({"ok": True})
        elif self.path == "/reset":
            SHARED["reset_done"].clear()
            with LOCK:
                SHARED["reset"] = (int(body.get("episode", 0)), bool(body.get("v4", False)))
            if not SHARED["reset_done"].wait(timeout=20):
                self._send({"error": "reset timed out"}, 500)
                return
            self._send(SHARED["reset_info"])
        elif self.path == "/teleport":  # debug: {"vial": "R0", "pos": [x,y,z]}
            with LOCK:
                SHARED["teleport"] = (body["vial"], body["pos"])
            self._send({"ok": True})
        elif self.path == "/home":
            with LOCK:
                SHARED["home"] = True
            self._send({"ok": True})
        else:
            self._send({"error": "unknown path"}, 404)


def main():
    sim = SimulationContext(SimulationCfg(dt=C.PHYSICS_DT, device="cuda:0"))
    scene = VialSortScene(sim, with_bin=args.with_bin)
    sim.reset()
    scene.initialize()

    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"sim server up on :{args.port}  ({len(EPISODES_V5)} v5 / {len(EPISODES_V4)} v4 episodes)")

    period = 1.0 / C.FPS
    while app.is_running():
        t0 = time.perf_counter()

        with LOCK:
            reset_req = SHARED["reset"]; SHARED["reset"] = None
            home_req = SHARED["home"]; SHARED["home"] = False
            target = SHARED["target"]; SHARED["target"] = None
            tele = SHARED["teleport"]; SHARED["teleport"] = None

        if tele is not None:
            key, pos = tele
            letter, k = key[0], int(key[1:])
            scene.teleport_vial(letter, k, pos)

        if reset_req is not None:
            idx, v4 = reset_req
            eps = EPISODES_V4 if v4 else EPISODES_V5
            ep = eps[idx % len(eps)]
            scene.set_scene(ep)
            scene.home()
            SHARED["reset_info"] = {"episode": ep.index, "task": ep.task, "dest": ep.dest,
                                    "left": ep.left, "right": ep.right,
                                    "target": list(ep.target), "v4": v4,
                                    "vials": scene.get_vial_positions()}
            SHARED["reset_done"].set()
            print(f"reset -> ep {ep.index} ({'v4' if v4 else 'v5'}): {ep.task!r}")
        if home_req:
            scene.home()
        if target:
            scene.set_joint_targets(target)

        scene.step()
        obs = {"state": scene.get_joint_state(), "images": encode_images(scene.get_images()),
               "t": time.time()}
        with LOCK:
            SHARED["obs"] = obs

        busy = time.perf_counter() - t0
        if busy < period:
            time.sleep(period - busy)

    server.shutdown()
    app.close()


if __name__ == "__main__":
    main()
