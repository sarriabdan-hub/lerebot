"""
VLA sim server — drop-in twin of ee/vla_server.py that drives the SIM arm.

Runs in the NORMAL lerobot env (py3.12). Loads a pi0/pi0.5 checkpoint, talks to
sim_server.py (isaac-venv, :6060) instead of a motor bus, and exposes the SAME
HTTP API as the real Thor server, so the existing tools work unchanged:

    ee/cv_run.py       --server http://127.0.0.1:8000     (full dashboard)
    ee/orchestrator.py --server http://127.0.0.1:8000     (VLM planner)

API (mirrors ee/vla_server.py):
    GET  /            minimal dashboard (3 MJPEG streams + execute/home/stop)
    GET  /health      {status, checkpoint, device}
    GET  /observe     {"images": {cam_top/cam_wrist/cam_side: b64 jpeg}, "live": bool}
    GET  /state       {busy, phase, task, duration, n_steps, last_stats, elapsed}
    GET  /stream/<cam>   MJPEG live stream (multipart/x-mixed-replace) — sim bonus
    POST /execute     {task, duration}        run the policy on the sim arm
    POST /home        {duration}              home the sim arm
    POST /stop        emergency stop (aborts a running execute)
    POST /tune        {n_action_steps}        live-tune without reload
    POST /reset       {episode, v4}           stage a sheet scene — sim bonus

Inference path = the real one (ee/rollout_pi0_lora.py): sim joints -> FK -> EE
obs -> policy -> EE action -> bounds+IK -> sim joint targets. --joint-space for
joint-space checkpoints.

Run (terminal 1: sim_server.py in isaac-venv; terminal 2, repo root):
    .venv/bin/python isaac/vla_sim_server.py --checkpoint <ckpt_dir>
"""

import argparse
import base64
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import cv2
import numpy as np
import torch

import sim_config as C
from eval_pi05 import DS_FEATURES_EE, DS_FEATURES_JOINT, load_policy
from sim_client import SimClient

from lerobot.model.kinematics import RobotKinematics
from lerobot.policies.utils import make_robot_action, prepare_observation_for_inference
from lerobot.processor import RobotProcessorPipeline
from lerobot.processor.converters import (
    observation_to_transition,
    robot_action_observation_to_transition,
    transition_to_observation,
    transition_to_robot_action,
)
from lerobot.robots.so_follower.robot_kinematic_processor import (
    EEBoundsAndSafety,
    ForwardKinematicsJointsToEE,
    InverseKinematicsEEToJoints,
)

STOP_EVENT = threading.Event()
ROBOT_LOCK = threading.Lock()
LIVE_LOCK = threading.Lock()
LIVE = {"busy": False, "phase": "idle", "task": "", "duration": 0.0, "n_steps": 0,
        "last_stats": None, "t_start": 0.0, "frames": {}, "raw_frames": {}}
STATE: dict = {}


def _set_live(**kw):
    with LIVE_LOCK:
        LIVE.update(kw)


def _encode(frames_rgb: dict) -> dict:
    out = {}
    for name, rgb in frames_rgb.items():
        ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                               [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ok:
            out[name] = base64.b64encode(buf.tobytes()).decode("ascii")
    return out


def frame_pump():
    """Background: poll the sim at ~12 Hz so /observe + /stream never block."""
    sim = SimClient(STATE["sim_host"], STATE["sim_port"])
    while True:
        try:
            _, imgs = sim.obs()
            _set_live(frames=_encode(imgs), raw_frames=imgs)
        except Exception:
            pass
        time.sleep(1 / 12)


def run_command(task: str, duration: float) -> dict:
    """The /execute loop — same shape as the real server's sync path."""
    sim: SimClient = STATE["sim"]
    STOP_EVENT.clear()
    _set_live(busy=True, phase="executing", task=task, duration=duration,
              n_steps=0, t_start=time.time())
    n = int(duration * C.FPS)
    lat = []
    t_begin = time.perf_counter()
    with torch.inference_mode():
        for i in range(n):
            if STOP_EVENT.is_set():
                _set_live(busy=False, phase="stopped")
                return {"aborted": True, "steps": i}
            t0 = time.perf_counter()
            joint_obs, imgs = sim.obs()
            if STATE["joint_space"]:
                obs_raw = dict(joint_obs)
            else:
                obs_raw = STATE["joints_to_ee"](dict(joint_obs))
            obs_raw.update({f"observation.images.{k}": v for k, v in imgs.items()})

            batch = STATE["pre"](prepare_observation_for_inference(obs_raw, STATE["device"], task))
            t_inf = time.perf_counter()
            action = STATE["post"](STATE["policy"].select_action(batch))
            lat.append(time.perf_counter() - t_inf)
            action_dict = make_robot_action(action, STATE["ds_features"])

            if STATE["joint_space"]:
                sim.act(action_dict)
            else:
                sim.act(STATE["ee_to_joints"]((action_dict, joint_obs)))

            _set_live(n_steps=i + 1)
            busy = time.perf_counter() - t0
            if busy < 1 / C.FPS:
                time.sleep(1 / C.FPS - busy)
    stats = {"steps": n, "wall_s": round(time.perf_counter() - t_begin, 2),
             "infer_ms_mean": round(1000 * float(np.mean(lat)), 1) if lat else None,
             "control_hz": round(n / max(time.perf_counter() - t_begin, 1e-6), 1)}
    _set_live(busy=False, phase="idle", last_stats=stats)
    return stats


def go_home(duration: float) -> dict:
    sim: SimClient = STATE["sim"]
    _set_live(busy=True, phase="homing", t_start=time.time())
    sim.home()
    time.sleep(min(duration, 3.0))  # teleport-home; brief settle for optics
    _set_live(busy=False, phase="idle")
    return {"homed": True}


DASHBOARD_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>VLA sim server</title><style>
 body{font-family:system-ui,sans-serif;margin:20px;background:#111;color:#eee}
 h1{font-size:18px} .cams{display:flex;gap:10px;flex-wrap:wrap}
 .cam{text-align:center;font-size:13px;color:#aaa} .cam img{max-width:400px;border:1px solid #444;border-radius:6px}
 button{padding:8px 14px;margin:4px;border:0;border-radius:6px;background:#2d6cdf;color:#fff;cursor:pointer}
 button.warn{background:#c0392b} input{padding:7px;border-radius:6px;border:1px solid #555;background:#222;color:#eee;width:420px}
 #status{white-space:pre-wrap;background:#000;padding:10px;border-radius:6px;margin-top:10px;min-height:20px}
</style></head><body>
<h1>&pi;0 VLA sim server</h1>
<div class="cams">
 <div class="cam"><img src="/stream/cam_top"><br>cam_top</div>
 <div class="cam"><img src="/stream/cam_side"><br>cam_side</div>
 <div class="cam"><img src="/stream/cam_wrist"><br>cam_wrist</div>
</div>
<div><input id="task" value="Put the light purple vial in the bin.">
 <input id="dur" value="30" style="width:60px"> s
 <input id="ep" value="3" style="width:50px"> ep</div>
<div>
 <button onclick="post('/reset',{episode:+document.getElementById('ep').value})">Reset scene</button>
 <button onclick="post('/home',{duration:3})">Home</button>
 <button onclick="post('/execute',{task:document.getElementById('task').value,duration:+document.getElementById('dur').value})">Execute</button>
 <button class="warn" onclick="post('/stop',{})">STOP</button>
</div>
<div id="status"></div>
<script>
async function post(p,b){const s=document.getElementById('status');s.textContent=p+' running...';
 const r=await fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
 s.textContent=p+' -> '+JSON.stringify(await r.json(),null,1);}
setInterval(async()=>{try{const r=await fetch('/state');const s=await r.json();
 if(s.busy)document.getElementById('status').textContent=`${s.phase} ${s.task} step ${s.n_steps} (${s.elapsed}s)`;}catch(e){}},1000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = DASHBOARD_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/health":
            self._send(200, {"status": "ok", "checkpoint": STATE["checkpoint"],
                             "device": str(STATE["device"]), "sim": True})
        elif self.path == "/observe":
            with LIVE_LOCK:
                frames, busy = dict(LIVE["frames"]), LIVE["busy"]
            self._send(200, {"images": frames, "live": busy})
        elif self.path == "/state":
            with LIVE_LOCK:
                s = {k: LIVE[k] for k in ("busy", "phase", "task", "duration", "n_steps", "last_stats")}
                s["elapsed"] = round(time.time() - LIVE["t_start"], 2) if LIVE["busy"] else 0.0
            self._send(200, s)
        elif self.path.startswith("/stream/"):
            self._stream(self.path.split("/stream/")[1])
        else:
            self._send(404, {"error": "unknown path"})

    def _stream(self, cam: str):
        """MJPEG: multipart/x-mixed-replace at ~12 fps from the frame pump."""
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        try:
            while True:
                with LIVE_LOCK:
                    rgb = LIVE["raw_frames"].get(cam)
                if rgb is not None:
                    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                                           [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ok:
                        data = buf.tobytes()
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                         + f"Content-Length: {len(data)}\r\n\r\n".encode()
                                         + data + b"\r\n")
                time.sleep(1 / 12)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        if self.path == "/stop":
            STOP_EVENT.set()
            print("[stop] EMERGENCY STOP requested")
            self._send(200, {"stopped": True})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
        except Exception as e:  # noqa: BLE001
            self._send(400, {"error": f"bad request: {e!r}"})
            return

        if self.path == "/tune":
            if req.get("n_action_steps") is not None:
                STATE["policy"].config.n_action_steps = int(req["n_action_steps"])
            self._send(200, {"n_action_steps": getattr(STATE["policy"].config, "n_action_steps", None)})
        elif self.path == "/reset":
            try:
                info = STATE["sim"].reset(episode=int(req.get("episode", 0)),
                                          v4=bool(req.get("v4", False)))
                info.pop("vials", None)
                self._send(200, info)
            except Exception as e:  # noqa: BLE001
                self._send(500, {"error": repr(e)})
        elif self.path == "/home":
            try:
                with ROBOT_LOCK:
                    self._send(200, go_home(float(req.get("duration", 4.0))))
            except Exception as e:  # noqa: BLE001
                _set_live(busy=False, phase="error")
                self._send(500, {"error": repr(e)})
        elif self.path == "/execute":
            try:
                task, duration = req["task"], float(req.get("duration", 30.0))
                print(f"[execute] task={task!r} duration={duration}s")
                with ROBOT_LOCK:
                    stats = run_command(task, duration)
                print(f"[execute] done: {stats}")
                self._send(200, stats)
            except Exception as e:  # noqa: BLE001
                _set_live(busy=False, phase="error")
                self._send(500, {"error": repr(e)})
        else:
            self._send(404, {"error": "unknown path"})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--sim-host", default="127.0.0.1")
    p.add_argument("--sim-port", type=int, default=6060)
    p.add_argument("--n-action-steps", type=int, default=15,
                   help="deployment default 15 (grasp-correction fix)")
    p.add_argument("--joint-space", action="store_true")
    args = p.parse_args()

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"loading {args.checkpoint} on {device} ...")
    policy, pre, post = load_policy(args.checkpoint, device, args.n_action_steps)

    kin = RobotKinematics(urdf_path=C.URDF_PATH, target_frame_name="gripper_frame_link",
                          joint_names=C.JOINT_NAMES)
    STATE.update(
        checkpoint=args.checkpoint, device=device, policy=policy, pre=pre, post=post,
        joint_space=args.joint_space,
        ds_features=DS_FEATURES_JOINT if args.joint_space else DS_FEATURES_EE,
        sim=SimClient(args.sim_host, args.sim_port),
        sim_host=args.sim_host, sim_port=args.sim_port,
        joints_to_ee=RobotProcessorPipeline(
            steps=[ForwardKinematicsJointsToEE(kinematics=kin, motor_names=C.JOINT_NAMES)],
            to_transition=observation_to_transition, to_output=transition_to_observation),
        ee_to_joints=RobotProcessorPipeline(
            steps=[EEBoundsAndSafety(end_effector_bounds=C.EE_BOUNDS, max_ee_step_m=C.MAX_EE_STEP_M),
                   InverseKinematicsEEToJoints(kinematics=kin, motor_names=C.JOINT_NAMES,
                                               initial_guess_current_joints=True)],
            to_transition=robot_action_observation_to_transition,
            to_output=transition_to_robot_action),
    )
    print("sim link:", STATE["sim"].ping())

    threading.Thread(target=frame_pump, daemon=True).start()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"VLA sim server on http://127.0.0.1:{args.port}  (dashboard at /)")
    print(f"cv_run:  .venv/bin/python ee/cv_run.py --server http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
