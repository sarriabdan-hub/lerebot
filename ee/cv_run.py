#!/usr/bin/env python3
"""
CV -> command -> VLA control panel (web UI).

This is the single thing you run on the workstation. It serves a polished local
dashboard in your browser and is a thin proxy to the warm π0 VLA server on Thor
(ee/vla_server.py). It gives you, in one place:

  * three big live camera feeds (top / wrist / side),
  * the VLA's PATH drawn live on each feed while it moves — a green motion trail
    with a red leading head, plus a green/amber/red glow around each camera that
    tracks what the arm is doing (executing / homing / idle-or-error),
  * classical-CV scene reading (the reliable slot_reader): it sees which vial is
    where and pre-builds the atomic command for the destination you pick,
  * Home and Execute buttons with their own durations — same homing concept as the
    old CLI (POST /home {duration}), just from the UI.

The robot, the model and the cameras all live on Thor; this process never touches
hardware. It only talks HTTP to --server, so it's safe to start/stop anytime.

Run it (web UI — the default):
    .venv/bin/python ee/cv_run.py                       # serve on http://127.0.0.1:8088
    .venv/bin/python ee/cv_run.py --open                # ...and open the browser
    .venv/bin/python ee/cv_run.py --server http://192.168.123.198:8000 --port 8088

TERMINAL mode (no browser — the old CLI, still here):
    .venv/bin/python ee/cv_run.py --dest-pos 3 --plan-only   # show CV grid + command, NO motion
    .venv/bin/python ee/cv_run.py --dest-pos 3 --cli         # read scene + execute (asks to confirm)
    .venv/bin/python ee/cv_run.py --dest-pos 3 --cli --yes   # ...execute without the prompt

--plan-only is the safety check: it prints the detected scene, writes the annotated
grid image to /tmp/slot_read.jpg, and shows the exact command — so you can confirm
the CV reading is right BEFORE the arm moves. The web UI's "Analyze scene" button
does the same thing in the browser.

Then open the printed URL. Requires ee/vla_server.py running on Thor (the live
camera/path feed needs the threaded /observe + /state endpoints it now exposes).
"""

import argparse
import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import slot_reader  # noqa: E402
from cam_align import estimate_transform  # noqa: E402

# Drift thresholds (match the training augmentation envelope). Beyond these the
# current camera pose is outside what the model trained on → UI flags it red.
ALIGN_DIR = Path(__file__).parent / "align"
TOL_TRANS_FRAC = 0.05   # 5% of width/height
TOL_ROT_DEG = 5.0
TOL_SCALE = 0.05        # 5%
_REF_CACHE: dict = {}   # camera -> reference image (BGR np array)

# ── Config (filled from argv in main, read by the request handler) ──────────────
CFG = {
    "server": "http://192.168.123.198:8000",   # the Thor VLA server
    "dest_rack": "right",
    "dest_pos": 3,
    "task": None,                              # explicit task override (else templated)
    "exec_dur": 30.0,
    "home_dur": 4.0,
}


# ── Thor proxy helpers ──────────────────────────────────────────────────────────

def _post(path: str, payload: dict, timeout: float = 600.0) -> dict:
    req = urllib.request.Request(
        f"{CFG['server']}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _get(path: str, timeout: float = 30.0) -> dict:
    with urllib.request.urlopen(f"{CFG['server']}{path}", timeout=timeout) as r:
        return json.loads(r.read())


def build_command(dest_pos: int, dest_rack: str | None = None) -> str:
    """The atomic command for the chosen destination.

    v2 is trained on both racks ({left,right} × pos {1,3,6}) so the prompt now
    controls rack AND position; an explicit --task still overrides the template."""
    rack = dest_rack or CFG["dest_rack"]
    return CFG["task"] or f"Place the red vial in position {dest_pos} of the {rack} rack."


# ── Classical-CV scene reading (reliable, local) ────────────────────────────────

def analyze_scene(dest_pos: int, dest_rack: str | None = None) -> dict:
    """Read the top camera with slot_reader and return scene + annotated image."""
    dest_rack = dest_rack or CFG["dest_rack"]
    slot_reader.SERVER = CFG["server"]
    img = slot_reader.fetch_top()                 # BGR, de-rotated upright
    calib = slot_reader.load_calib()
    vials = slot_reader.detect_vials(img)
    if calib:
        vials = slot_reader.assign_slots(vials, calib)
    annotated = slot_reader.annotate(img, vials, calib)

    ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82])
    image_b64 = base64.b64encode(buf.tobytes()).decode("ascii") if ok else ""

    scene = {"left": {}, "right": {}, "unassigned": []}
    vlist = []
    for v in vials:
        rack, pos = v.get("rack"), v.get("position")
        vlist.append({"color": v["color"], "rack": rack, "position": pos})
        if rack:
            scene[rack][str(pos)] = v["color"]
        else:
            scene["unassigned"].append(v["color"])

    src_rack = "left" if dest_rack == "right" else "right"
    has_src = any(v.get("rack") == src_rack for v in vials)
    return {
        "scene": scene,
        "vials": vlist,
        "image": image_b64,
        "calibrated": bool(calib),
        "src_rack": src_rack,
        "has_src": has_src,
        "command": build_command(dest_pos, dest_rack),
    }


# ── Live camera-alignment drift (vs the recording-pose reference) ────────────────

def _load_ref(camera: str):
    """Cache the reference PNG for a camera (from ee/extract_ref_frame.py)."""
    if camera not in _REF_CACHE:
        path = ALIGN_DIR / f"reference_{camera}.png"
        _REF_CACHE[camera] = cv2.imread(str(path)) if path.exists() else None
    return _REF_CACHE[camera]


def check_alignment(camera: str = "cam_top") -> dict:
    """Compare the CURRENT camera frame (from Thor /observe) to the recording-pose
    reference, returning per-axis drift and whether each axis is within tolerance."""
    ref = _load_ref(camera)
    if ref is None:
        return {"error": f"no reference for {camera} (run ee/extract_ref_frame.py)"}
    obs = _get("/observe", timeout=10).get("images", {})
    b64 = obs.get(camera)
    if not b64:
        return {"error": f"server returned no {camera} frame"}
    cur = cv2.imdecode(np.frombuffer(base64.b64decode(b64), np.uint8), cv2.IMREAD_COLOR)
    cur = cv2.resize(cur, (ref.shape[1], ref.shape[0]))
    t = estimate_transform(ref, cur)
    if not t.get("ok"):
        return {"error": t.get("reason", "transform failed")}
    h, w = ref.shape[:2]
    dx_frac, dy_frac = abs(t["tx"]) / w, abs(t["ty"]) / h
    scale_off = abs(t["scale"] - 1)
    rot_off = abs(t["rot"])
    within = (dx_frac < TOL_TRANS_FRAC and dy_frac < TOL_TRANS_FRAC
              and rot_off < TOL_ROT_DEG and scale_off < TOL_SCALE)
    return {
        "camera": camera,
        "dx": round(t["tx"], 1), "dy": round(t["ty"], 1),
        "dx_pct": round(dx_frac * 100, 1), "dy_pct": round(dy_frac * 100, 1),
        "rot": round(t["rot"], 2),
        "zoom_pct": round((t["scale"] - 1) * 100, 1),
        "within": within,
        "exceeds": [k for k, bad in (
            ("dx", dx_frac >= TOL_TRANS_FRAC), ("dy", dy_frac >= TOL_TRANS_FRAC),
            ("rot", rot_off >= TOL_ROT_DEG), ("zoom", scale_off >= TOL_SCALE)) if bad],
    }


# ── Terminal mode (the old CLI: plan-only grid check + execute) ──────────────────

CLI_OUT_PATH = "/tmp/slot_read.jpg"


def run_cli(plan_only: bool, assume_yes: bool) -> None:
    """No web server — read the scene in the terminal, show the grid, optionally run.

    --plan-only stops after printing the scene + command and saving the annotated
    grid image, so you can verify the CV is right before any motion.
    """
    try:
        h = _get("/health", timeout=10)
        print(f"Server OK — checkpoint={h.get('checkpoint')} device={h.get('device')}\n")
    except Exception as e:  # noqa: BLE001
        print(f"⚠ could not reach VLA server at {CFG['server']} (/health: {e!r})\n")

    try:
        info = analyze_scene(CFG["dest_pos"])
    except Exception as e:  # noqa: BLE001
        print(f"✗ CV read failed (is the VLA server up and the top camera live?): {e!r}")
        return
    if info.get("image"):
        Path(CLI_OUT_PATH).write_bytes(base64.b64decode(info["image"]))

    print("CV scene:")
    for rack in ("left", "right"):
        filled = ", ".join(f"pos{p}={c}" for p, c in sorted(info["scene"][rack].items())) or "empty"
        print(f"  {rack} rack: {filled}")
    if info["scene"]["unassigned"]:
        print(f"  unassigned (no nearby slot): {info['scene']['unassigned']}")
    if not info["calibrated"]:
        print("  (no slot calibration yet — boxes only; run slot_reader.py --calibrate-coords)")
    if not info["has_src"]:
        print(f"\n⚠ CV sees no vial in the {info['src_rack']} (source) rack. "
              "Place one, or continue anyway (base_v1 ignores the prompt).")

    print(f"\nAnnotated grid image -> {CLI_OUT_PATH}   (open it to check the CV is right)")
    cmd = info["command"]
    print(f"Command -> {cmd!r}")

    if plan_only:
        return

    if not assume_yes:
        ans = input("\nExecute on the robot? [Enter=yes / q=quit] ").strip().lower()
        if ans == "q":
            return
    stats = _post("/execute", {"task": cmd, "duration": CFG["exec_dur"]})
    print(f"\nResult: {stats}")


# ── Dashboard ───────────────────────────────────────────────────────────────────
# Served at "/". Everything below is the single-page app; placeholders are filled
# from CFG before serving (no % / .format, to keep the JS template literals intact).

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vial-Sort · VLA Control</title>
<style>
  :root{
    --bg:#0a0d14; --panel:#121724; --panel2:#171d2c; --line:#243044;
    --txt:#e8edf6; --mut:#8a97ad; --accent:#3b82f6;
    --green:#22c55e; --amber:#f59e0b; --red:#ef4444;
    --radius:14px; --shadow:0 8px 30px rgba(0,0,0,.45);
    font-synthesis:none;
  }
  *{box-sizing:border-box}
  html,body{height:100%}
  body{
    margin:0; background:radial-gradient(1200px 600px at 70% -10%,#16203a 0%,var(--bg) 55%);
    color:var(--txt); font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    -webkit-font-smoothing:antialiased;
  }
  header{
    display:flex; align-items:center; gap:16px; padding:14px 22px;
    border-bottom:1px solid var(--line); background:rgba(10,13,20,.7);
    backdrop-filter:blur(10px); position:sticky; top:0; z-index:10;
  }
  .brand{display:flex; align-items:center; gap:11px; font-weight:700; letter-spacing:.3px}
  .brand .dot{width:11px;height:11px;border-radius:50%;background:var(--mut);box-shadow:0 0 0 4px rgba(255,255,255,.04)}
  .brand small{font-weight:500;color:var(--mut);letter-spacing:.5px;text-transform:uppercase;font-size:11px}
  .grow{flex:1}
  .pill{
    display:inline-flex; align-items:center; gap:8px; padding:6px 12px; border-radius:999px;
    background:var(--panel2); border:1px solid var(--line); color:var(--mut); font-size:12.5px;
  }
  .pill b{color:var(--txt);font-weight:600}
  .pill .led{width:8px;height:8px;border-radius:50%;background:var(--mut)}
  .pill.ok .led{background:var(--green);box-shadow:0 0 8px var(--green)}
  .pill.bad .led{background:var(--red);box-shadow:0 0 8px var(--red)}

  main{display:grid; grid-template-columns:1fr 380px; gap:18px; padding:18px; max-width:1700px; margin:0 auto}
  @media (max-width:1100px){ main{grid-template-columns:1fr} }

  /* cameras */
  .cams{display:grid; grid-template-columns:repeat(3,1fr); gap:14px}
  @media (max-width:1400px){ .cams{grid-template-columns:1fr 1fr} }
  @media (max-width:760px){ .cams{grid-template-columns:1fr} }
  .cam{
    position:relative; background:#000; border-radius:var(--radius); overflow:hidden;
    border:2px solid var(--line); box-shadow:var(--shadow); transition:border-color .25s, box-shadow .25s;
  }
  .cam.execute{border-color:var(--green); box-shadow:0 0 0 1px var(--green),0 0 26px rgba(34,197,94,.45)}
  .cam.home{border-color:var(--amber); box-shadow:0 0 0 1px var(--amber),0 0 26px rgba(245,158,11,.40)}
  .cam.error{border-color:var(--red); box-shadow:0 0 0 1px var(--red),0 0 26px rgba(239,68,68,.45)}
  .cam canvas{display:block; width:100%; aspect-ratio:4/3; background:#05070c}
  .cam .tag{
    position:absolute; top:10px; left:10px; padding:4px 10px; border-radius:8px; font-size:12px;
    font-weight:700; letter-spacing:.6px; background:rgba(5,7,12,.62); border:1px solid var(--line);
  }
  .cam .live{
    position:absolute; top:10px; right:10px; padding:4px 9px; border-radius:8px; font-size:11px;
    font-weight:700; letter-spacing:.6px; background:rgba(5,7,12,.62); border:1px solid var(--line); color:var(--mut);
  }
  .cam .live.on{color:#fff; border-color:var(--green)}
  .cam .live.on::before{content:"●  "; color:var(--green)}

  .statusbar{
    display:flex; align-items:center; gap:14px; margin-top:14px; padding:12px 16px;
    background:var(--panel); border:1px solid var(--line); border-radius:var(--radius);
  }
  .phase{display:flex;align-items:center;gap:9px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;font-size:13px}
  .phase .orb{width:12px;height:12px;border-radius:50%;background:var(--mut)}
  .phase.execute .orb{background:var(--green);box-shadow:0 0 10px var(--green)}
  .phase.home .orb{background:var(--amber);box-shadow:0 0 10px var(--amber)}
  .phase.error .orb{background:var(--red);box-shadow:0 0 10px var(--red)}
  .bar{flex:1;height:9px;border-radius:999px;background:#0c1119;overflow:hidden;border:1px solid var(--line)}
  .bar > i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--accent),var(--green));transition:width .2s}
  .metrics{display:flex;gap:18px;font-size:12.5px;color:var(--mut)}
  .metrics b{color:var(--txt);font-variant-numeric:tabular-nums}

  /* side panel */
  .side{display:flex;flex-direction:column;gap:16px}
  .card{background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); box-shadow:var(--shadow)}
  .card > h2{
    margin:0; padding:13px 16px; font-size:12px; letter-spacing:1.2px; text-transform:uppercase; color:var(--mut);
    border-bottom:1px solid var(--line); display:flex; align-items:center; gap:8px;
  }
  .card .body{padding:15px 16px; display:flex; flex-direction:column; gap:12px}
  label.fld{display:flex;flex-direction:column;gap:6px;font-size:12px;color:var(--mut)}
  input[type=text],input[type=number],textarea{
    width:100%; padding:10px 12px; border-radius:10px; border:1px solid var(--line);
    background:#0c111b; color:var(--txt); font-size:14px; font-family:inherit; resize:vertical;
  }
  input:focus,textarea:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(59,130,246,.18)}
  .row{display:flex;gap:10px;align-items:flex-end}
  .row > *{flex:1}
  .seg{display:flex;gap:6px;flex-wrap:wrap}
  .seg button{
    flex:1; min-width:38px; padding:9px 0; border-radius:9px; border:1px solid var(--line);
    background:#0c111b; color:var(--mut); cursor:pointer; font-weight:700; font-size:13px; transition:.15s;
  }
  .seg button:hover{border-color:var(--accent);color:var(--txt)}
  .seg button.on{background:var(--accent);border-color:var(--accent);color:#fff;box-shadow:0 4px 14px rgba(59,130,246,.4)}
  button.act{
    width:100%; padding:13px; border:0; border-radius:11px; font-size:14.5px; font-weight:700; cursor:pointer;
    color:#fff; letter-spacing:.3px; transition:.15s; background:var(--accent);
  }
  button.act:hover{filter:brightness(1.08)}
  button.act:active{transform:translateY(1px)}
  button.act:disabled{opacity:.5;cursor:not-allowed;filter:none}
  button.act.go{background:linear-gradient(120deg,#16a34a,#22c55e)}
  button.act.warn{background:linear-gradient(120deg,#d97706,#f59e0b)}
  button.act.stop{background:linear-gradient(120deg,#b91c1c,#ef4444);margin-top:4px}
  .hint{font-size:12px;color:var(--mut);line-height:1.45}
  .cmd{
    background:#0c111b;border:1px dashed var(--line);border-radius:10px;padding:10px 12px;
    font-size:13px;color:#cfe0ff;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-word;
  }
  .scene{display:flex;flex-direction:column;gap:8px;font-size:13px}
  .rack{display:flex;align-items:center;gap:8px}
  .rack .name{width:46px;color:var(--mut);text-transform:uppercase;font-size:11px;letter-spacing:.5px}
  .slots{display:flex;gap:5px;flex:1}
  .slot{
    flex:1;height:30px;border-radius:7px;border:1px solid var(--line);background:#0c111b;
    display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:var(--mut);
  }
  .slot.full{color:#05070c}
  .cvimg{width:100%;border-radius:10px;border:1px solid var(--line);display:none}
  #console{
    background:#05070c;border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:0;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:#b6c2d6;
    max-height:190px;overflow:auto;white-space:pre-wrap;line-height:1.5;
  }
  #console .t{color:#5b6b85}
  .legend{display:flex;gap:16px;align-items:center;font-size:11.5px;color:var(--mut);margin-top:10px;flex-wrap:wrap}
  .legend span{display:inline-flex;align-items:center;gap:6px}
  .swatch{width:12px;height:12px;border-radius:3px}
</style>
</head>
<body>
<header>
  <div class="brand">
    <span class="dot" id="connDot"></span>
    VIAL-SORT <small>VLA control</small>
  </div>
  <div class="grow"></div>
  <span class="pill" id="alignPill" style="display:none"><span class="led"></span><span id="alignPillTxt"></span></span>
  <span class="pill" id="healthPill"><span class="led"></span><span id="healthTxt">connecting…</span></span>
</header>
<div id="driftBanner" style="display:none;background:linear-gradient(90deg,#7f1d1d,#b91c1c);color:#fff;padding:10px 22px;font-weight:700;text-align:center;letter-spacing:.3px"></div>

<main>
  <section>
    <div class="cams" id="cams">
      <div class="cam" data-cam="cam_top">
        <canvas width="640" height="480"></canvas>
        <span class="tag">TOP</span><span class="live">idle</span>
      </div>
      <div class="cam" data-cam="cam_wrist">
        <canvas width="640" height="480"></canvas>
        <span class="tag">WRIST</span><span class="live">idle</span>
      </div>
      <div class="cam" data-cam="cam_side">
        <canvas width="640" height="480"></canvas>
        <span class="tag">SIDE</span><span class="live">idle</span>
      </div>
    </div>

    <div class="statusbar">
      <div class="phase" id="phase"><span class="orb"></span><span id="phaseTxt">idle</span></div>
      <div class="bar"><i id="progress"></i></div>
      <div class="metrics">
        <span>steps <b id="mSteps">0</b></span>
        <span>t <b id="mTime">0.0</b>s</span>
        <span>lat <b id="mLat">–</b></span>
        <span>hz <b id="mHz">–</b></span>
      </div>
    </div>
    <div class="legend">
      <span><i class="swatch" style="background:var(--green)"></i> VLA path (trail)</span>
      <span><i class="swatch" style="background:var(--red);border-radius:50%"></i> path head (now)</span>
      <span><i class="swatch" style="background:var(--green)"></i> executing glow</span>
      <span><i class="swatch" style="background:var(--amber)"></i> homing glow</span>
    </div>
  </section>

  <aside class="side">
    <div class="card">
      <h2>Scene · classical CV</h2>
      <div class="body">
        <button class="act" onclick="analyze()">Analyze scene</button>
        <div class="scene" id="sceneView">
          <div class="rack"><span class="name">Left</span><div class="slots" id="rackLeft"></div></div>
          <div class="rack"><span class="name">Right</span><div class="slots" id="rackRight"></div></div>
        </div>
        <img class="cvimg" id="cvimg">
        <div class="hint" id="sceneHint">Reads the top camera to see which vial is where, then pre-builds the command below.</div>
      </div>
    </div>

    <div class="card">
      <h2>Execute</h2>
      <div class="body">
        <label class="fld">Destination rack
          <div class="seg" id="rackSeg"></div>
        </label>
        <label class="fld">Destination position
          <div class="seg" id="destSeg"></div>
        </label>
        <label class="fld">Command sent to the VLA
          <textarea id="task" rows="2">__DEFAULT_TASK__</textarea>
        </label>
        <div class="row">
          <label class="fld">Duration (s)
            <input type="number" id="execDur" value="__EXEC_DUR__" min="1" max="300" step="1">
          </label>
          <button class="act go" id="execBtn" onclick="execute()">▶ Execute</button>
        </div>
        <button class="act stop" id="stopBtn" onclick="estop()">■ EMERGENCY STOP</button>
        <div class="hint">Resets the action queue and runs the 30&nbsp;Hz control loop for the duration. Watch the green path on the cameras. STOP halts motion immediately (arm holds pose).</div>
      </div>
    </div>

    <div class="card">
      <h2>Home</h2>
      <div class="body">
        <div class="row">
          <label class="fld">Duration (s)
            <input type="number" id="homeDur" value="__HOME_DUR__" min="1" max="20" step="0.5">
          </label>
          <button class="act warn" id="homeBtn" onclick="goHome()">⌂ Home arm</button>
        </div>
        <div class="hint">Smoothly interpolates the arm from wherever it is to the trained rest pose — safe to run anytime.</div>
      </div>
    </div>

    <div class="card">
      <h2>Camera alignment · vs recording pose</h2>
      <div class="body">
        <div class="row" style="align-items:center">
          <div class="seg" id="alignCamSeg" style="flex:2"></div>
          <button class="act" style="flex:1" onclick="checkAlign()">Check now</button>
        </div>
        <div id="alignBox" class="cmd">not checked yet</div>
        <div class="hint">Polls every 3s. Turns red + alerts if any axis leaves the ±5% / ±5° training band. Reference = ee/align/reference_*.png (sessions 3-6 pose).</div>
      </div>
    </div>

    <div class="card">
      <h2>Live tuning · no restart</h2>
      <div class="body">
        <div class="row" style="align-items:center;gap:10px">
          <label style="flex:1">smooth α (joints)
            <input type="number" id="tSmooth" value="0.3" min="0.1" max="1" step="0.05" style="width:100%">
          </label>
          <label style="flex:1">gripper α
            <input type="number" id="tGrip" value="0.5" min="0.1" max="1" step="0.05" style="width:100%">
          </label>
          <label style="flex:1">n_action_steps
            <input type="number" id="tNas" value="15" min="1" max="50" step="1" style="width:100%">
          </label>
        </div>
        <div class="row" style="align-items:center;gap:10px;margin-top:8px">
          <label style="flex:1">filter
            <select id="tFilter" style="width:100%">
              <option value="ema">ema (fixed α)</option>
              <option value="oneeuro">1-euro (adaptive)</option>
            </select>
          </label>
          <label style="flex:1">euro min_cutoff
            <input type="number" id="tEuroMc" value="1.0" min="0.1" max="10" step="0.1" style="width:100%">
          </label>
          <label style="flex:1">euro beta
            <input type="number" id="tEuroBeta" value="0.05" min="0" max="2" step="0.01" style="width:100%">
          </label>
        </div>
        <button class="act" onclick="applyTune()">Apply (takes effect next Execute)</button>
        <div class="hint" id="tuneHint">EMA: lower α = smoother but laggier. 1-euro: lower min_cutoff = smoother at rest; higher beta = less lag on fast moves. Applies on the NEXT Execute — no reload.</div>
      </div>
    </div>

    <div class="card">
      <h2>Eval · score this checkpoint</h2>
      <div class="body">
        <div class="row" style="align-items:center">
          <label style="flex:1">checkpoint
            <input type="text" id="ckptLabel" value="v4_8000" style="width:100%">
          </label>
          <button class="act" style="flex:1" onclick="evalReset()">↻ Restart matrix</button>
        </div>
        <div class="scene" id="evalScenario" style="margin:10px 0;padding:12px;border-radius:8px;background:#0f172a;border:1px solid #334155">
          <div style="font-weight:700;font-size:15px" id="evScenarioTitle">—</div>
          <div style="margin-top:6px" id="evScenarioSetup">press Restart matrix to begin</div>
          <div style="margin-top:6px;color:#93c5fd" id="evScenarioPrompt"></div>
        </div>
        <button class="act go" id="evExecBtn" onclick="evalExecute()">▶ Home + Execute this scenario</button>
        <div class="hint">Homes the arm, then sends THIS scenario's prompt to the robot. After it finishes, tap the outcome below — it logs the row (with the scenario) and advances to the next.</div>
        <div style="margin-top:10px;font-weight:700">Outcome — tap one:</div>
        <div id="evalBtns" style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:6px">
          <button class="act" style="background:#166534" onclick="evalLog('PASS')">✓ Pass<br><small>grabbed source → placed named slot</small></button>
          <button class="act" style="background:#854d0e" onclick="evalLog('miss_grasp')">✋ Missed grasp<br><small>right place, grabbed air</small></button>
          <button class="act" style="background:#9a3412" onclick="evalLog('wrong_slot')">↔ Wrong slot<br><small>correct rack, wrong position</small></button>
          <button class="act" style="background:#991b1b" onclick="evalLog('wrong_rack')">✗ Wrong rack<br><small>went to the wrong rack (language fail)</small></button>
          <button class="act" style="background:#7f1d1d" onclick="evalLog('collision')">💥 Collision<br><small>hit rack / itself / knocked over</small></button>
          <button class="act" style="background:#581c87" onclick="evalLog('dropped')">⬇ Dropped<br><small>picked up then dropped mid-way</small></button>
          <button class="act" style="background:#334155" onclick="evalLog('no_move')">∅ No move<br><small>didn't move / just oscillated</small></button>
          <button class="act" style="background:#475569" onclick="evalSkip()">» Skip / redo<br><small>don't log, advance</small></button>
        </div>
        <div class="hint" id="evalTally" style="margin-top:10px">no trials logged yet</div>
      </div>
    </div>

    <div class="card">
      <h2>Console</h2>
      <div class="body"><pre id="console"></pre></div>
    </div>
  </aside>
</main>

<script>
const $  = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
let DEST = __DEST_POS__;
let RACK = "__DEST_RACK__";
let taskEdited = false;
let busyLocal = false;          // an execute/home POST is in flight from this UI

// ---- eval matrix -----------------------------------------------------------
// Each trial: where to put the RED vial, the prompt, and the destination tag.
const EVAL_TRIALS = [
  {dest:"right p6", source:"LEFT slot 1",  prompt:"Place the red vial in position 6 of the right rack."},
  {dest:"right p6", source:"LEFT slot 3",  prompt:"Place the red vial in position 6 of the right rack."},
  {dest:"right p6", source:"LEFT slot 6",  prompt:"Place the red vial in position 6 of the right rack."},
  {dest:"left p1",  source:"RIGHT slot 1", prompt:"Place the red vial in position 1 of the left rack."},
  {dest:"left p1",  source:"RIGHT slot 3", prompt:"Place the red vial in position 1 of the left rack."},
  {dest:"left p1",  source:"RIGHT slot 6", prompt:"Place the red vial in position 1 of the left rack."},
  {dest:"left p6",  source:"RIGHT slot 1", prompt:"Place the red vial in position 6 of the left rack."},
  {dest:"left p6",  source:"RIGHT slot 3", prompt:"Place the red vial in position 6 of the left rack."},
  {dest:"left p6",  source:"RIGHT slot 6", prompt:"Place the red vial in position 6 of the left rack."},
];
let evalIdx = 0;          // index into EVAL_TRIALS (cycles forever)
let evalDone = 0;         // total logged trials this checkpoint
let evalPass = 0;         // total PASS this checkpoint

function evalCur(){ return EVAL_TRIALS[evalIdx % EVAL_TRIALS.length]; }
function evalRender(){
  const t = evalCur();
  $('#evScenarioTitle').textContent = `Trial ${evalDone+1}  ·  destination = ${t.dest}`;
  $('#evScenarioSetup').innerHTML = `1) Put the <b>RED</b> vial at: <b>${t.source}</b> &nbsp;(blue distractor: anywhere)`;
  $('#evScenarioPrompt').textContent = `2) Prompt: ${t.prompt}`;
}
function evalReset(){
  evalIdx = 0; evalDone = 0; evalPass = 0;
  evalRender();
  $('#evalTally').textContent = "matrix restarted — 9 scenarios, cycles. Do as many as you like.";
  log('eval matrix restarted for '+$('#ckptLabel').value);
}
async function evalExecute(){
  if(busyLocal) return;
  const t = evalCur();
  $('#task').value = t.prompt;       // mirror into the main Execute box for visibility
  log('eval: homing then executing → '+t.prompt);
  busyLocal = true; $('#evExecBtn').disabled = true;
  try{
    await fetch('/api/home',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({duration:parseFloat($('#homeDur').value)})});
    const r = await fetch('/api/execute',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({task:t.prompt,duration:parseFloat($('#execDur').value)})});
    log('eval execute done: '+JSON.stringify(await r.json()));
  }catch(e){ log('eval execute failed: '+e); }
  busyLocal = false; $('#evExecBtn').disabled = false;
}
async function evalLog(outcome){
  const t = evalCur();
  const row = {checkpoint:$('#ckptLabel').value, destination:t.dest, source:t.source,
               prompt:t.prompt, outcome:outcome};
  try{
    await fetch('/api/eval_log',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(row)});
  }catch(e){ log('eval_log save failed: '+e); }
  evalDone++; if(outcome==='PASS') evalPass++;
  log(`logged [${t.dest} / ${t.source}] → ${outcome}`);
  evalIdx++; evalRender();
  $('#evalTally').textContent =
    `${$('#ckptLabel').value}: ${evalPass}/${evalDone} passed (${Math.round(100*evalPass/Math.max(evalDone,1))}%)  ·  saved to ee/eval_results.csv`;
}
function evalSkip(){ evalIdx++; evalRender(); log('eval: skipped, advanced'); }

// ---- live tuning -----------------------------------------------------------
async function applyTune(){
  const body={smooth_alpha:parseFloat($('#tSmooth').value),
              gripper_alpha:parseFloat($('#tGrip').value),
              n_action_steps:parseInt($('#tNas').value),
              filter:$('#tFilter').value,
              euro_min_cutoff:parseFloat($('#tEuroMc').value),
              euro_beta:parseFloat($('#tEuroBeta').value)};
  try{
    const r=await fetch('/api/tune',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)});
    const j=await r.json();
    $('#tuneHint').textContent='applied: '+JSON.stringify(j)+' — press Execute to feel it';
    log('tune applied: '+JSON.stringify(j));
  }catch(e){ log('tune failed: '+e); }
}

// ---- console ---------------------------------------------------------------
function log(msg, cls){
  const el = $('#console');
  const t = new Date().toLocaleTimeString();
  el.textContent += `[${t}] ${msg}\n`;
  el.scrollTop = el.scrollHeight;
}

// ---- destination selectors -------------------------------------------------
function buildRackSeg(){
  const seg = $('#rackSeg'); seg.innerHTML='';
  for(const r of ['left','right']){
    const b=document.createElement('button');
    b.textContent=r.toUpperCase(); if(r===RACK) b.classList.add('on');
    b.onclick=()=>{ RACK=r; buildRackSeg(); refreshCommand(); };
    seg.appendChild(b);
  }
}
function buildDestSeg(){
  const seg = $('#destSeg'); seg.innerHTML='';
  for(let p=1;p<=6;p++){
    const b=document.createElement('button');
    b.textContent=p; if(p===DEST) b.classList.add('on');
    b.onclick=()=>{ DEST=p; buildDestSeg(); refreshCommand(); };
    seg.appendChild(b);
  }
}
function refreshCommand(){
  $('#task').value = `Place the red vial in position ${DEST} of the ${RACK} rack.`;
}
$('#task').addEventListener('input', ()=>{ taskEdited=true; });

// ---- scene -----------------------------------------------------------------
const VIAL_HEX = {red:'#ef4444',green:'#22c55e',blue:'#3b82f6',cyan:'#06b6d4',yellow:'#eab308'};
function renderRack(id, slots){
  const wrap=$(id); wrap.innerHTML='';
  for(let p=1;p<=6;p++){
    const c=slots[p];
    const d=document.createElement('div');
    d.className='slot'+(c?' full':'');
    d.textContent=p;
    if(c){ d.style.background=VIAL_HEX[c]||'#94a3b8'; d.title=c; }
    wrap.appendChild(d);
  }
}
async function analyze(){
  log('Analyzing scene…');
  try{
    const j = await (await fetch(`/api/cv?dest_pos=${DEST}&dest_rack=${RACK}`)).json();
    if(j.error){ log('CV error: '+j.error); return; }
    renderRack('#rackLeft', j.scene.left||{});
    renderRack('#rackRight', j.scene.right||{});
    if(j.image){ const im=$('#cvimg'); im.src='data:image/jpeg;base64,'+j.image; im.style.display='block'; }
    let h = j.calibrated ? '' : 'No slot calibration yet — boxes only. ';
    h += j.has_src ? `Source vial present in the ${j.src_rack} rack.` :
                     `⚠ No vial seen in the ${j.src_rack} (source) rack.`;
    $('#sceneHint').textContent = h;
    log('Scene read: '+JSON.stringify(j.scene));
  }catch(e){ log('analyze failed: '+e); }
}

// ---- live cameras + VLA path overlay --------------------------------------
const CAMS = ['cam_top','cam_wrist','cam_side'];
const view = {};   // per-cam render state
CAMS.forEach(name=>{
  const card = document.querySelector(`.cam[data-cam="${name}"]`);
  view[name] = {
    card, canvas: card.querySelector('canvas'),
    ctx: card.querySelector('canvas').getContext('2d'),
    live: card.querySelector('.live'),
    img: new Image(), ready:false,
    diff: document.createElement('canvas'),   // small offscreen for motion detection
    prev: null, trail: [],
  };
  const v=view[name]; v.diff.width=96; v.diff.height=72; v.dctx=v.diff.getContext('2d',{willReadFrequently:true});
  v.tracking=false;
  // process each fully-decoded frame here (src is set async in tick()).
  v.img.onload=()=>{
    v.ready=true;
    if(v.tracking){ const m=detectMotion(v); if(m) pushTrail(v,m); }
    else { v.prev=null; }
  };
});

const DW=96, DH=72, PIXTHRESH=42, MINMOVE=8, MAXMOVE=DW*DH*0.45;

function detectMotion(v){
  // returns normalized centroid {x,y} of the moving region, or null
  v.dctx.drawImage(v.img, 0,0, DW,DH);
  const cur = v.dctx.getImageData(0,0,DW,DH).data;
  let res=null;
  if(v.prev){
    let sx=0, sy=0, n=0;
    for(let i=0,p=0;i<cur.length;i+=4,p++){
      const d=Math.abs(cur[i]-v.prev[i])+Math.abs(cur[i+1]-v.prev[i+1])+Math.abs(cur[i+2]-v.prev[i+2]);
      if(d>PIXTHRESH){ const x=p%DW, y=(p/DW)|0; sx+=x; sy+=y; n++; }
    }
    if(n>MINMOVE && n<MAXMOVE) res={x:sx/n/DW, y:sy/n/DH};
  }
  v.prev=cur;
  return res;
}

function pushTrail(v, pt){
  v.trail.push({x:pt.x, y:pt.y, life:1});
  if(v.trail.length>64) v.trail.shift();
}
function fadeTrail(v, amt){
  for(const p of v.trail) p.life-=amt;
  v.trail = v.trail.filter(p=>p.life>0);
}

function drawCam(v, tracking){
  const {ctx,canvas}=v, W=canvas.width, H=canvas.height;
  if(v.ready) ctx.drawImage(v.img,0,0,W,H); else { ctx.fillStyle='#05070c'; ctx.fillRect(0,0,W,H); }
  const tr=v.trail;
  if(tr.length>1){
    ctx.lineCap='round'; ctx.lineJoin='round';
    for(let i=1;i<tr.length;i++){
      const a=tr[i], b=tr[i-1];
      ctx.strokeStyle=`rgba(34,197,94,${0.85*a.life})`;
      ctx.lineWidth=2 + 6*a.life;
      ctx.beginPath(); ctx.moveTo(b.x*W,b.y*H); ctx.lineTo(a.x*W,a.y*H); ctx.stroke();
    }
  }
  if(tr.length && tracking){
    const h=tr[tr.length-1];
    ctx.save();
    ctx.shadowColor='rgba(239,68,68,.9)'; ctx.shadowBlur=18;
    ctx.fillStyle='#ef4444';
    ctx.beginPath(); ctx.arc(h.x*W,h.y*H,9,0,Math.PI*2); ctx.fill();
    ctx.restore();
    ctx.strokeStyle='rgba(255,255,255,.85)'; ctx.lineWidth=2;
    ctx.beginPath(); ctx.arc(h.x*W,h.y*H,9,0,Math.PI*2); ctx.stroke();
  }
}

function applyGlow(phase){
  CAMS.forEach(name=>{
    const c=view[name].card;
    c.classList.remove('execute','home','error');
    if(phase==='execute') c.classList.add('execute');
    else if(phase==='home') c.classList.add('home');
    else if(phase==='error') c.classList.add('error');
  });
}

let polling=false;
async function tick(){
  if(polling) return; polling=true;
  try{
    const j = await (await fetch('/api/live')).json();
    const st = j.state||{}; const imgs=j.images||{};
    const phase = st.phase || (j.reachable===false?'error':'idle');
    const tracking = phase==='execute';
    applyGlow(phase);

    // status bar
    const ph=$('#phase'); ph.className='phase '+(phase==='idle'?'':phase);
    $('#phaseTxt').textContent = phase;
    $('#mSteps').textContent = st.n_steps||0;
    $('#mTime').textContent = (st.elapsed||0).toFixed(1);
    const prog = st.busy && st.duration ? Math.min(100,100*(st.elapsed/st.duration)) : (busyLocal?100:0);
    $('#progress').style.width = prog+'%';

    // cameras — set src (decode is async; the per-frame trail work runs in img.onload)
    for(const name of CAMS){
      const v=view[name];
      v.tracking = tracking;
      if(imgs[name]){
        v.img.src='data:image/jpeg;base64,'+imgs[name];
        v.live.textContent = st.busy?'live':'idle';
        v.live.classList.toggle('on', !!st.busy);
      }
    }
  }catch(e){
    applyGlow('error');
    $('#healthPill').className='pill bad'; $('#healthTxt').textContent='server unreachable';
    $('#connDot').style.background='var(--red)';
  }finally{ polling=false; }
}

// render loop (decoupled from the network poll so the trail animates/fades smoothly)
let lastFrame=performance.now();
function raf(now){
  const dt=Math.min((now-lastFrame)/1000, 0.1); lastFrame=now;
  const tracking = $('#phaseTxt').textContent==='execute';
  for(const name of CAMS){
    const v=view[name];
    fadeTrail(v, dt*(tracking?0.45:1.3));   // ~2.2s fade while tracking, faster when idle
    drawCam(v, tracking);
  }
  requestAnimationFrame(raf);
}

// ---- actions ---------------------------------------------------------------
async function execute(){
  if(busyLocal) return;
  const task=$('#task').value.trim(); const dur=parseFloat($('#execDur').value);
  if(!task){ log('command is empty'); return; }
  busyLocal=true; $('#execBtn').disabled=true; $('#homeBtn').disabled=true;
  $('#mLat').textContent='–'; $('#mHz').textContent='–';
  log(`EXECUTE ${dur}s — "${task}"`);
  try{
    const r = await fetch('/api/execute',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({task, duration:dur})});
    const j = await r.json();
    if(j.error){ log('execute error: '+j.error); }
    else{
      if(j.infer_lat_ms_mean!=null) $('#mLat').textContent=j.infer_lat_ms_mean+'ms';
      if(j.control_hz_mean!=null) $('#mHz').textContent=j.control_hz_mean;
      log('done: '+JSON.stringify(j));
    }
  }catch(e){ log('execute failed: '+e); }
  finally{ busyLocal=false; $('#execBtn').disabled=false; $('#homeBtn').disabled=false; $('#progress').style.width='0%'; }
}

async function estop(){
  log('■ EMERGENCY STOP');
  try{
    const r = await fetch('/api/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    log('stopped: '+JSON.stringify(await r.json()));
  }catch(e){ log('stop failed: '+e); }
  // Treat stop like a clean end-of-timer: free the UI so the next Execute works.
  busyLocal=false; $('#execBtn').disabled=false; $('#homeBtn').disabled=false;
  $('#progress').style.width='0%';
}

async function goHome(){
  if(busyLocal) return;
  const dur=parseFloat($('#homeDur').value);
  busyLocal=true; $('#execBtn').disabled=true; $('#homeBtn').disabled=true;
  log(`HOME ${dur}s`);
  try{
    const r = await fetch('/api/home',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({duration:dur})});
    const j = await r.json();
    log(j.error?('home error: '+j.error):('homed: '+JSON.stringify(j)));
  }catch(e){ log('home failed: '+e); }
  finally{ busyLocal=false; $('#execBtn').disabled=false; $('#homeBtn').disabled=false; $('#progress').style.width='0%'; }
}

// ---- health ----------------------------------------------------------------
async function health(){
  try{
    const j = await (await fetch('/api/health')).json();
    if(j.reachable===false) throw new Error('down');
    const ckpt = (j.checkpoint||'').split('/').filter(Boolean).slice(-1)[0] || '?';
    $('#healthPill').className='pill ok';
    $('#healthTxt').innerHTML = `<b>${j.device||'?'}</b> · ${ckpt}`;
    $('#connDot').style.background='var(--green)';
    $('#connDot').style.boxShadow='0 0 10px var(--green)';
  }catch(e){
    $('#healthPill').className='pill bad'; $('#healthTxt').textContent='server unreachable';
    $('#connDot').style.background='var(--red)';
  }
}

// ---- camera alignment ------------------------------------------------------
let ALIGN_CAM = 'cam_top';
let alignAlerted = false;
function buildAlignCamSeg(){
  const seg=$('#alignCamSeg'); seg.innerHTML='';
  for(const c of ['cam_top','cam_side','cam_wrist']){
    const b=document.createElement('button');
    b.textContent=c.replace('cam_','').toUpperCase(); if(c===ALIGN_CAM) b.classList.add('on');
    b.onclick=()=>{ ALIGN_CAM=c; buildAlignCamSeg(); checkAlign(); };
    seg.appendChild(b);
  }
}
async function checkAlign(){
  const box=$('#alignBox');
  try{
    const j = await (await fetch(`/api/align?camera=${ALIGN_CAM}`)).json();
    if(j.error){ box.textContent='align: '+j.error; setBanner(false,null); return; }
    const line = `${j.camera}: dx=${j.dx}px(${j.dx_pct}%) dy=${j.dy}px(${j.dy_pct}%) rot=${j.rot}° zoom=${j.zoom_pct}%`;
    box.textContent = line + (j.within ? '  ✅ in band' : '  ⚠ OUT OF BAND: '+j.exceeds.join(', '));
    box.style.color = j.within ? '#7CFC9A' : '#ffb4b4';
    setBanner(!j.within, j);
  }catch(e){ box.textContent='align check failed: '+e; }
}
function setBanner(bad, j){
  const ban=$('#driftBanner'), pill=$('#alignPill'), ptxt=$('#alignPillTxt');
  if(bad){
    ban.style.display='block';
    ban.textContent = `⚠ CAMERA ${j.camera.toUpperCase()} OUT OF BAND — ${j.exceeds.join(', ')} exceed ±5%/±5° (dx ${j.dx_pct}% dy ${j.dy_pct}% rot ${j.rot}° zoom ${j.zoom_pct}%). Re-align before trusting results.`;
    pill.style.display='inline-flex'; pill.className='pill bad'; ptxt.textContent='drift';
    if(!alignAlerted){ alignAlerted=true; log('⚠ ALIGNMENT OUT OF BAND: '+j.exceeds.join(', ')); }
  }else{
    ban.style.display='none';
    if(j){ pill.style.display='inline-flex'; pill.className='pill ok'; ptxt.textContent='aligned'; }
    alignAlerted=false;
  }
}

// ---- boot ------------------------------------------------------------------
buildAlignCamSeg();
buildRackSeg();
buildDestSeg();
health(); analyze(); checkAlign();
requestAnimationFrame(raf);
setInterval(tick, 120);
setInterval(health, 5000);
setInterval(checkAlign, 3000);
</script>
</body>
</html>"""


def render_dashboard() -> str:
    return (DASHBOARD_HTML
            .replace("__DEFAULT_TASK__", build_command(CFG["dest_pos"]))
            .replace("__EXEC_DUR__", str(int(CFG["exec_dur"])))
            .replace("__HOME_DUR__", str(CFG["home_dur"]))
            .replace("__DEST_POS__", str(CFG["dest_pos"]))
            .replace("__DEST_RACK__", CFG["dest_rack"]))


# ── HTTP handler (local web server + proxy to Thor) ─────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quieter logs
        return

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- GET --
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, qs = parsed.path, urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._html(render_dashboard())

        elif path == "/api/health":
            try:
                self._json(200, {**_get("/health", timeout=5), "reachable": True})
            except Exception as e:  # noqa: BLE001
                self._json(200, {"reachable": False, "error": repr(e)})

        elif path == "/api/state":
            # lightweight: just Thor /state (incl. last_stats with jitter_deg) — no images
            try:
                self._json(200, _get("/state", timeout=5))
            except Exception as e:  # noqa: BLE001
                self._json(200, {"error": repr(e)})

        elif path == "/api/live":
            # one round-trip for the browser: merge Thor /state + /observe.
            out = {"reachable": True}
            try:
                out["state"] = _get("/state", timeout=5)
            except Exception as e:  # noqa: BLE001
                out["reachable"] = False
                out["state"] = {"phase": "error", "error": repr(e)}
            try:
                out["images"] = _get("/observe", timeout=10).get("images", {})
            except Exception:  # noqa: BLE001
                out["images"] = {}
            self._json(200, out)

        elif path == "/api/align":
            cam = qs.get("camera", ["cam_top"])[0]
            try:
                self._json(200, check_alignment(cam))
            except Exception as e:  # noqa: BLE001
                self._json(200, {"error": repr(e)})

        elif path == "/api/cv":
            try:
                dest_pos = int(qs.get("dest_pos", [CFG["dest_pos"]])[0])
            except (ValueError, TypeError):
                dest_pos = CFG["dest_pos"]
            dest_rack = qs.get("dest_rack", [CFG["dest_rack"]])[0]
            if dest_rack not in ("left", "right"):
                dest_rack = CFG["dest_rack"]
            try:
                self._json(200, analyze_scene(dest_pos, dest_rack))
            except Exception as e:  # noqa: BLE001
                self._json(200, {"error": repr(e)})

        else:
            self._json(404, {"error": "unknown path"})

    # -- POST --
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
        except Exception as e:  # noqa: BLE001
            self._json(400, {"error": f"bad request: {e!r}"})
            return

        if path == "/api/execute":
            try:
                stats = _post("/execute", {"task": req["task"],
                                           "duration": float(req.get("duration", CFG["exec_dur"]))})
                self._json(200, stats)
            except Exception as e:  # noqa: BLE001
                self._json(200, {"error": repr(e)})

        elif path == "/api/stop":
            try:
                self._json(200, _post("/stop", {}, timeout=10))
            except Exception as e:  # noqa: BLE001
                self._json(200, {"error": repr(e)})

        elif path == "/api/home":
            try:
                stats = _post("/home", {"duration": float(req.get("duration", CFG["home_dur"]))},
                              timeout=120)
                self._json(200, stats)
            except Exception as e:  # noqa: BLE001
                self._json(200, {"error": repr(e)})

        elif path == "/api/tune":
            try:
                self._json(200, _post("/tune", req, timeout=10))
            except Exception as e:  # noqa: BLE001
                self._json(200, {"error": repr(e)})

        elif path == "/api/eval_log":
            try:
                import csv as _csv
                import datetime as _dt
                results = Path(__file__).parent / "eval_results.csv"
                new = not results.exists()
                with open(results, "a", newline="") as fh:
                    wr = _csv.writer(fh)
                    if new:
                        wr.writerow(["timestamp", "checkpoint", "destination",
                                     "source", "prompt", "outcome"])
                    wr.writerow([_dt.datetime.now().isoformat(timespec="seconds"),
                                 req.get("checkpoint", ""), req.get("destination", ""),
                                 req.get("source", ""), req.get("prompt", ""),
                                 req.get("outcome", "")])
                self._json(200, {"ok": True, "file": str(results)})
            except Exception as e:  # noqa: BLE001
                self._json(200, {"error": repr(e)})

        else:
            self._json(404, {"error": "unknown path"})


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Vial-sort VLA control panel (web UI).")
    ap.add_argument("--server", default=CFG["server"], help="Thor VLA server base URL")
    ap.add_argument("--host", default="127.0.0.1", help="host to serve the UI on")
    ap.add_argument("--port", type=int, default=8088, help="port to serve the UI on")
    ap.add_argument("--dest-rack", default="right", choices=["right", "left"])
    ap.add_argument("--dest-pos", type=int, default=3)
    ap.add_argument("--task", default=None,
                    help="explicit command override (else the trained template is used)")
    ap.add_argument("--duration", type=float, default=30.0, help="default execute duration (s)")
    ap.add_argument("--home-duration", type=float, default=4.0, help="default home duration (s)")
    ap.add_argument("--open", action="store_true", help="open the UI in a browser on start")
    # terminal mode (no web server) — the old CLI behavior:
    ap.add_argument("--plan-only", action="store_true",
                    help="terminal: print CV scene + grid image + command, NO robot motion")
    ap.add_argument("--cli", action="store_true",
                    help="terminal: read scene, build command, execute on the robot (asks to confirm)")
    ap.add_argument("--yes", action="store_true",
                    help="with --cli: execute without the confirmation prompt")
    args = ap.parse_args()

    CFG.update(server=args.server.rstrip("/"), dest_rack=args.dest_rack, dest_pos=args.dest_pos,
               task=args.task, exec_dur=args.duration, home_dur=args.home_duration)

    # Terminal mode: do the CV check / execute in the console and exit (no web UI).
    if args.plan_only or args.cli or args.yes:
        run_cli(plan_only=args.plan_only, assume_yes=args.yes)
        return

    url = f"http://{args.host}:{args.port}"
    print(f"Vial-sort control panel → {url}")
    print(f"  proxying to VLA server: {CFG['server']}")
    try:
        h = _get("/health", timeout=5)
        print(f"  server OK — checkpoint={h.get('checkpoint')} device={h.get('device')}")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ VLA server not reachable yet ({e!r}) — the UI will keep retrying.")

    if args.open:
        webbrowser.open(url)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")


if __name__ == "__main__":
    main()
