#!/usr/bin/env python3
"""
LIVE camera re-alignment — watch the drift shrink in real time as you move the camera.

Runs on the WORKSTATION. Polls the warm VLA server's /observe a few times a second,
compares each live frame against a REFERENCE screenshot from your recordings, and
serves a web page that continuously shows:
  - a red/green overlay (red = original recording, green = live; colour fringe = drift),
  - the measured translation / rotation / zoom,
  - plain "do this / do that" instructions that update as you nudge the camera.

No rerunning. Open the page, watch the numbers, stop when it says ✅ ALIGNED.

WHY POLL THE SERVER (not /dev/video* directly):
  - The cameras live on Thor and the server already holds them open (direct device
    access would be "busy").
  - The RealSense exposes several /dev/video nodes (color/depth/IR); the server
    already publishes its COLOR stream as cam_side — no wrong-node guessing.
  - The workstation's OpenCV is headless, so we render in the browser, not a window.

USAGE (workstation):
  1. Put your ORIGINAL recording screenshots in ee/align/ (see REFERENCES below):
        reference_cam_top.png, reference_cam_wrist.png, reference_cam_side.png
     (from the Hugging Face dataset frames / the rerun.io visualizer.)
  2. Start it:   .venv/bin/python ee/cam_align_live.py
  3. Open:       http://localhost:8765
  4. Pick a camera, move it while watching the overlay + instructions update live.
"""

import argparse
import base64
import json
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from cam_align import estimate_transform, instructions  # reuse the validated CV core

# Reference (original recording) screenshot per camera. Drop the files here.
REFERENCES = {
    "cam_top":   "ee/align/old_camera_reference_top_FULL.png",     # original TOP view (primary for placement)
    "cam_wrist": "ee/align/old_camera_reference_wrist_FULL.png",   # original WRIST view
    "cam_side":  "ee/align/old_camera_reference_side_FULL.png",    # original SIDE view (RealSense colour)
}

SERVER = "http://192.168.123.198:8000"
_REF_CACHE: dict = {}


def load_reference(camera: str):
    if camera not in _REF_CACHE:
        path = REFERENCES.get(camera)
        img = cv2.imread(path, cv2.IMREAD_COLOR) if path else None
        _REF_CACHE[camera] = img  # may be None if the file isn't there yet
    return _REF_CACHE[camera]


def fetch_live(camera: str, server: str):
    """Latest colour frame for `camera` from the server's /observe."""
    d = json.load(urllib.request.urlopen(f"{server}/observe", timeout=15))["images"]
    if camera not in d:
        return None, sorted(d)
    buf = np.frombuffer(base64.b64decode(d[camera]), np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR), sorted(d)


def overlay_b64(ref, cur) -> str:
    """Red = reference, green = current; gridlines. Aligned => grey (no colour fringe)."""
    h, w = ref.shape[:2]
    g_ref = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
    g_cur = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY)
    ov = np.zeros((h, w, 3), np.uint8)
    ov[:, :, 2] = g_ref
    ov[:, :, 1] = g_cur
    for x in range(0, w, max(w // 8, 1)):
        cv2.line(ov, (x, 0), (x, h), (70, 70, 70), 1)
    for y in range(0, h, max(h // 6, 1)):
        cv2.line(ov, (0, y), (w, y), (70, 70, 70), 1)
    ok, jpg = cv2.imencode(".jpg", ov, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(jpg.tobytes()).decode("ascii")


def compute_frame(camera: str, server: str) -> dict:
    ref = load_reference(camera)
    if ref is None:
        return {"ok": False, "msg": f"No reference for {camera}. Put it at {REFERENCES.get(camera)}"}
    cur, have = fetch_live(camera, server)
    if cur is None:
        return {"ok": False, "msg": f"{camera} not in /observe (have: {have})"}
    h, w = ref.shape[:2]
    if cur.shape[:2] != (h, w):
        cur = cv2.resize(cur, (w, h))
    t = estimate_transform(ref, cur)
    res = {"ok": True, "overlay": overlay_b64(ref, cur), "camera": camera}
    if not t["ok"]:
        res["lines"] = [f"Can't measure drift: {t['reason']}",
                        "Make sure the live view shows the same fixed scene (racks/table) as the reference."]
        res["metrics"] = ""
        return res
    res["metrics"] = (f"dx={t['tx']:+.0f}px  dy={t['ty']:+.0f}px   "
                      f"rot={t['rot']:+.2f}°   zoom={t['scale']:.3f} "
                      f"({(t['scale']-1)*100:+.1f}%)   [{t['inliers']}/{t['matches']} pts]")
    res["lines"] = instructions(t, w, h)
    res["aligned"] = any("ALIGNED" in ln for ln in res["lines"])
    return res


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>cam align (live)</title><style>
 body{font-family:system-ui,sans-serif;margin:18px;background:#111;color:#eee}
 #ov{max-width:680px;border:1px solid #444;border-radius:6px;display:block}
 button{padding:7px 12px;margin:3px;border:0;border-radius:6px;background:#2d6cdf;color:#fff;cursor:pointer}
 button.sel{background:#1b8f4d}
 #metrics{font-family:monospace;margin:8px 0;color:#9cf}
 #lines{white-space:pre-wrap;background:#000;padding:10px;border-radius:6px;font-size:15px}
 #banner{font-size:20px;margin:6px 0;min-height:26px}
</style></head><body>
<h2>Live camera alignment</h2>
<div>camera:
 <button id="b_cam_top" class="sel" onclick="pick('cam_top')">cam_top</button>
 <button id="b_cam_wrist" onclick="pick('cam_wrist')">cam_wrist</button>
 <button id="b_cam_side" onclick="pick('cam_side')">cam_side</button>
 &nbsp; red = original &nbsp; green = live &nbsp;(aligned ⇒ grey, no colour fringe)
</div>
<div id="banner"></div>
<img id="ov" src="">
<div id="metrics"></div>
<div id="lines"></div>
<script>
let cam='cam_top';
function pick(c){cam=c;for(const k of ['cam_top','cam_wrist','cam_side'])
  document.getElementById('b_'+k).className=(k===c?'sel':'');}
async function tick(){try{
  const r=await fetch('/frame?camera='+cam);const j=await r.json();
  if(!j.ok){document.getElementById('lines').textContent=j.msg;
    document.getElementById('banner').textContent='';document.getElementById('metrics').textContent='';return;}
  document.getElementById('ov').src='data:image/jpeg;base64,'+j.overlay;
  document.getElementById('metrics').textContent=j.metrics;
  document.getElementById('lines').textContent=(j.lines||[]).join('\\n');
  document.getElementById('banner').textContent=j.aligned?'✅ ALIGNED':'… adjusting';
  document.getElementById('banner').style.color=j.aligned?'#3f5':'#fa3';
}catch(e){document.getElementById('banner').textContent='server busy / unreachable…';}}
setInterval(tick,800);tick();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_url = SERVER

    def log_message(self, *a):
        return

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            body = PAGE.encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif u.path == "/frame":
            cam = parse_qs(u.query).get("camera", ["cam_top"])[0]
            try:
                payload = compute_frame(cam, self.server_url)
            except Exception as e:  # noqa: BLE001
                payload = {"ok": False, "msg": f"error: {e!r}"}
            body = json.dumps(payload).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=SERVER, help="warm VLA server (provides the live frames)")
    ap.add_argument("--port", type=int, default=8765, help="local port to view the page on")
    args = ap.parse_args()
    Handler.server_url = args.server
    print(f"Live alignment UI: http://localhost:{args.port}   (frames from {args.server})")
    print("Drop reference screenshots in ee/align/ (reference_cam_top.png etc). Ctrl+C to stop.")
    HTTPServer(("0.0.0.0", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
