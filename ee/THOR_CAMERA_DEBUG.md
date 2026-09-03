# Thor RealSense `cam_side` fix — RESOLVED

`ee/vla_server.py` now reaches **`VLA server ready on http://0.0.0.0:8000`** and `/health`
returns `{"status": "ok", ...}`. Fix was two lines in `ee/rollout_pi0_lora.py`
`build_robot_and_pipelines` (~line 128).

## The fix

In `ee/rollout_pi0_lora.py`:
1. **Move `cam_side` (RealSense) to first** in the `cameras` dict.
2. **Add `fourcc="MJPG"`** to both OpenCV cameras (`cam_top`, `cam_wrist`).

```python
cameras = {
    "cam_side": RealSenseCameraConfig(
        serial_number_or_name="052622071016",
        fps=FPS, width=640, height=480, color_mode="rgb", warmup_s=10,
    ),
    "cam_top": OpenCVCameraConfig(
        index_or_path=".../4.2.2:1.0-video-index0",
        fps=FPS, width=640, height=480, color_mode="rgb", fourcc="MJPG",
    ),
    "cam_wrist": OpenCVCameraConfig(
        index_or_path=".../4.2.4:1.0-video-index0",
        fps=FPS, width=640, height=480, color_mode="rgb", fourcc="MJPG",
    ),
}
```

`SO101Follower.connect()` iterates `cameras.values()` in insertion order, so dict order
IS connect order.

## Root cause

**USB-2 bandwidth saturation, not threading.**

The two OpenCV cams were requesting uncompressed 640×480×30fps and were connected
BEFORE the RealSense. When RealSense's `pipeline.start()` returned and the read thread
called `try_wait_for_frames`, the USB-2 controller had zero headroom, so every read
came back `status=False`. That's the "read thread alive, zero frames" symptom.

CLAUDE.md called both requirements out explicitly:
- "**Camera startup order matters**: RealSense MUST connect before USB cameras or it times out."
- "USB cameras must use `fourcc=\"MJPG\"` — uncompressed at 30fps saturates the USB controller."

Both had regressed in `rollout_pi0_lora.py`. Nothing wrong with the wrapper or with
librealsense on this box — the setup around it violated hardware constraints.

## What the debug doc's hypothesis got wrong

The doc suggested the read thread couldn't see frames because `pipeline.start()` was
called in the main thread while `wait_for_frames()` ran in a background thread. That
hypothesis is **falsified** on this Jetson. Direct test:

```python
p = rs.pipeline(); c = rs.config()
rs.config.enable_device(c, '052622071016')
c.enable_stream(rs.stream.color, 640, 480, rs.format.rgb8, 30)
p.start(c); time.sleep(1.0)

results = {'ok': 0, 'fail': 0}
def reader():
    for i in range(30):
        ret, frame = p.try_wait_for_frames(timeout_ms=2000)
        results['ok' if (ret and frame is not None) else 'fail'] += 1
t = threading.Thread(target=reader); t.start(); t.join()
# → {'ok': 30, 'fail': 0}
```

Start-in-main + read-in-thread gets 30/30 frames every time. The wrapper's threading
model is fine; don't move `pipeline.start()` into `_read_loop`.

## Verification

`camera_realsense.py` (the wrapper) is unchanged from what was already patched in
this tree — no new edits needed there. The current wrapper is fine; the `.bak` file
predates the settle-after-start and the guarded read loop and can be deleted.

Reproducer of the failure (before the fix, or if you regress it):

```bash
conda run -n lerobot --no-capture-output python -c "
import sys; sys.path.insert(0, '/home/robot/dev/lerebot')
from ee.rollout_pi0_lora import build_robot_and_pipelines
follower, _, _ = build_robot_and_pipelines(dry_run=False, ik_from_prev_solution=True)
follower.disconnect()
"
```

Broken (RS last, no MJPG): `TimeoutError: ... after 10000 ms. Read thread alive: True.`
Fixed (RS first, MJPG on): `CONNECTED`, all 3 cams stream stable frames for 10s+.

End-to-end:
```bash
conda run -n lerobot --no-capture-output \
  python -u /home/robot/dev/lerebot/ee/vla_server.py \
  --checkpoint /home/robot/dev/lerebot/ckpt_v4_016000 \
  --n-action-steps 15 --async-chunks \
  --ik-prev-solution --filter ema --trace-motors \
  --log-file /tmp/vla_runs.jsonl
# → "VLA server ready on http://0.0.0.0:8000  (init done — stays warm)"
# → curl http://127.0.0.1:8000/health → {"status": "ok", ...}
```

## Notes for the workstation

- The workstation doesn't run cameras, but if you deploy the same
  `build_robot_and_pipelines` anywhere with 3 cams on one USB-2 controller,
  keep the RS-first + MJPG pattern.
- The two previously-mentioned in-flight wrapper patches (settle after `start()`,
  guarded `_read_loop`) are still in `camera_realsense.py` — keep them, they're
  cheap and independently correct even though they weren't the root cause here.
- Only `ee/rollout_pi0_lora.py` changed. Nothing else needed.
