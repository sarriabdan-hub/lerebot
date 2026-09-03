#!/usr/bin/env python3
"""Grab ONE frame from cam_top (OpenCV) + cam_side (RealSense) -> /tmp/cam_*.png.
Run ON THOR in the lerobot env, with NOTHING else holding the cameras
(pkill -f ee/vla_server.py first). Uses the exact record paths/resolution so the
frames match what gets recorded.

    conda run -n lerobot --no-capture-output python /home/robot/dev/lerebot/ee/grab_frames.py
"""
import time

import cv2
import numpy as np

CAM_TOP = "/dev/v4l/by-path/platform-a80aa10000.usb-usb-0:4.2.2:1.0-video-index0"
RS_SERIAL = "052622071016"

# ── cam_top (OpenCV, MJPG 640x480) ───────────────────────────────────────────
cap = cv2.VideoCapture(CAM_TOP)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
frame = None
for _ in range(20):                       # throw away warmup/dark frames
    ok, f = cap.read()
    if ok:
        frame = f
    time.sleep(0.03)
cap.release()
if frame is not None:
    cv2.imwrite("/tmp/cam_top.png", frame)
    print("cam_top  -> /tmp/cam_top.png")
else:
    print("cam_top  FAILED to read (is another process holding it?)")

# ── cam_side (RealSense color 640x480) ───────────────────────────────────────
import pyrealsense2 as rs

pipe = rs.pipeline()
cfg = rs.config()
cfg.enable_device(RS_SERIAL)
cfg.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
pipe.start(cfg)
color = None
for _ in range(30):                       # warmup (auto-exposure settles)
    fr = pipe.wait_for_frames()
    color = np.asanyarray(fr.get_color_frame().get_data())
pipe.stop()
cv2.imwrite("/tmp/cam_side.png", color)
print("cam_side -> /tmp/cam_side.png")
print("done. scp both back to the WS.")
