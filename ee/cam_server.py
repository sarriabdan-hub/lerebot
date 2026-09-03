#!/usr/bin/env python3
"""
Lightweight CAMERA-ONLY server for Thor — opens the 3 cameras and serves /observe,
with NO policy/model load and NO motors. Startup is seconds, not minutes.

This exists so you can do camera alignment (ee/cam_align_live.py) without paying the
~3-minute π0 load that ee/vla_server.py needs. It serves the SAME /observe shape the
full server does, so cam_align_live.py works against it unchanged.

  GET /health   -> {status, cameras: [...]}
  GET /observe  -> {images: {cam_top|cam_wrist|cam_side: <b64 jpeg>}}
  GET /         -> a tiny live preview page

⚠ Only ONE process can hold the cameras. Run EITHER this OR vla_server.py, not both.

USAGE (Thor terminal, from the lerobot repo root):
    /home/robot/miniforge3/envs/lerobot/bin/python ee/cam_server.py --port 8000

Then on the WORKSTATION:
    .venv/bin/python ee/cam_align_live.py            # polls http://192.168.123.198:8000/observe
"""

import argparse
import base64
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lerobot.cameras.opencv.camera_opencv import OpenCVCamera
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.cameras.realsense.camera_realsense import RealSenseCamera
from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig

FPS = 30

# Same camera configuration as ee/rollout_pi0_lora.py build_robot_and_pipelines —
# keep these in sync if the hardware moves.
CAM_CONFIGS = {
    "cam_top": OpenCVCameraConfig(
        index_or_path="/dev/v4l/by-path/platform-a80aa10000.usb-usb-0:4.2.2:1.0-video-index0",
        fps=FPS, width=640, height=480, color_mode="rgb",
    ),
    "cam_wrist": OpenCVCameraConfig(
        index_or_path="/dev/v4l/by-path/platform-a80aa10000.usb-usb-0:4.2.4:1.0-video-index0",
        fps=FPS, width=640, height=480, color_mode="rgb",
    ),
    "cam_side": RealSenseCameraConfig(
        serial_number_or_name="052622071016",
        fps=FPS, width=640, height=480, color_mode="rgb", warmup_s=3,
    ),
}

CAMS: dict = {}   # name -> connected camera (only the ones that opened)


def connect_cameras() -> None:
    for name, cfg in CAM_CONFIGS.items():
        try:
            cam = OpenCVCamera(cfg) if isinstance(cfg, OpenCVCameraConfig) else RealSenseCamera(cfg)
            cam.connect()
            CAMS[name] = cam
            print(f"  + {name} connected")
        except Exception as e:  # noqa: BLE001 — keep serving whichever cameras work
            print(f"  - {name} FAILED to open: {e!r}")


def capture_images() -> dict:
    """{short_cam_name: b64 jpeg} — RGB read converted to BGR (matches vla_server)."""
    out = {}
    for name, cam in CAMS.items():
        try:
            frame = cam.read()                       # RGB (color_mode="rgb")
            bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                out[name] = base64.b64encode(buf.tobytes()).decode("ascii")
        except Exception as e:  # noqa: BLE001
            print(f"[observe] {name} read failed: {e!r}")
    return out


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>cam server</title>
<style>body{font-family:system-ui,sans-serif;margin:18px;background:#0c0f16;color:#e8edf6}
img{max-width:420px;border:1px solid #2a3550;border-radius:8px;margin:4px}
.cam{display:inline-block;text-align:center;margin:6px}</style></head><body>
<h2>Camera server <span style="color:#8a97ad">— live preview (no model loaded)</span></h2>
<div id="cams"></div>
<script>
async function tick(){try{const j=await (await fetch('/observe')).json();const c=document.getElementById('cams');
 c.innerHTML='';for(const[k,v]of Object.entries(j.images||{})){const d=document.createElement('div');d.className='cam';
 d.innerHTML='<div>'+k+'</div><img src="data:image/jpeg;base64,'+v+'">';c.appendChild(d);}}catch(e){}}
setInterval(tick,500);tick();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        return

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", PAGE.encode())
        elif self.path == "/health":
            self._send(200, "application/json",
                       json.dumps({"status": "ok", "cameras": sorted(CAMS)}).encode())
        elif self.path == "/observe":
            try:
                self._send(200, "application/json", json.dumps({"images": capture_images()}).encode())
            except Exception as e:  # noqa: BLE001
                self._send(500, "application/json", json.dumps({"error": repr(e)}).encode())
        else:
            self._send(404, "application/json", json.dumps({"error": "unknown path"}).encode())


def main():
    ap = argparse.ArgumentParser(description="Camera-only server (no model) for alignment.")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    print("Opening cameras (no model load)...")
    connect_cameras()
    if not CAMS:
        print("✗ No cameras opened — nothing to serve. Check the device paths / RealSense serial.")
        return

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    print(f"\nCamera server ready on http://{args.host}:{args.port}   cameras={sorted(CAMS)}")
    print("  GET /observe   GET /health   (open / for a live preview)\nCtrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        for cam in CAMS.values():
            try:
                cam.disconnect()
            except Exception:  # noqa: BLE001
                pass


if __name__ == "__main__":
    main()
