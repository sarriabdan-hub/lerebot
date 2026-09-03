#!/usr/bin/env python3
"""
CV slot reader for vial-sort — reliable, free, local (no VLM).

The camera and racks are FIXED, so "which of 6 holes holds a colored vial" is a
classical-CV problem. This:
  1. detects vials by color  -> bounding boxes ("where each vial is"),
  2. (after a one-time 4-click calibration) maps each vial to rack + slot number,
  3. saves an annotated image and prints the structured scene state.

Pulls the TOP camera from the warm VLA server and de-rotates it CCW90 (arm at top,
LEFT rack = source, RIGHT rack = goal; position 1 = nearest the arm, 6 = far end) —
same orientation the planner uses.

Usage (workstation):
    # one-time calibration (opens a window; click 4 slot centers, in order):
    .venv/bin/python ee/slot_reader.py --calibrate

    # read the scene -> annotated image + structured state:
    .venv/bin/python ee/slot_reader.py
    .venv/bin/python ee/slot_reader.py --show          # also pop a window

Calibration is saved to ee/slot_calib.json. Re-run --calibrate if the camera moves.
"""

import argparse
import base64
import json
import urllib.request
from pathlib import Path

import cv2
import numpy as np

SERVER = "http://192.168.123.198:8000"
CALIB_PATH = Path(__file__).parent / "slot_calib.json"
OUT_PATH = "/tmp/slot_read.jpg"
N_SLOTS = 6

# HSV color ranges (OpenCV H is 0-179). Add colors here as needed.
# V floors kept low (vials can be dark) but S floors high so dark/gray rack holes
# (low saturation) are not picked up as vials.
COLOR_RANGES = {
    "red":    [((0, 100, 50), (10, 255, 255)), ((170, 100, 50), (179, 255, 255))],
    "cyan":   [((78, 70, 25), (100, 255, 255))],
    "blue":   [((101, 80, 40), (130, 255, 255))],
    "green":  [((40, 70, 40), (77, 255, 255))],
    "yellow": [((20, 110, 90), (34, 255, 255))],
}
DRAW_BGR = {"red": (0, 0, 255), "cyan": (255, 255, 0), "blue": (255, 0, 0),
            "green": (0, 255, 0), "yellow": (0, 255, 255)}
MIN_VIAL_AREA = 250  # px; filters specular noise


def fetch_top() -> np.ndarray:
    """Top camera, de-rotated CCW90 to upright (matches the planner)."""
    d = json.load(urllib.request.urlopen(f"{SERVER}/observe", timeout=30))["images"]
    buf = np.frombuffer(base64.b64decode(d["cam_top"]), np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)


def detect_vials(img: np.ndarray) -> list[dict]:
    """Return [{color, bbox(x,y,w,h), centroid(cx,cy)}] for each colored blob."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    vials = []
    for color, ranges in COLOR_RANGES.items():
        mask = np.zeros(hsv.shape[:2], np.uint8)
        for lo, hi in ranges:
            mask |= cv2.inRange(hsv, np.array(lo), np.array(hi))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            if cv2.contourArea(c) < MIN_VIAL_AREA:
                continue
            x, y, w, h = cv2.boundingRect(c)
            vials.append({"color": color, "bbox": (x, y, w, h),
                          "centroid": (x + w / 2, y + h / 2)})
    return vials


def load_calib():
    if CALIB_PATH.exists():
        return json.loads(CALIB_PATH.read_text())
    return None


def assign_slots(vials: list[dict], calib: dict) -> list[dict]:
    """Snap each vial centroid to the nearest calibrated slot center."""
    centers = []  # (rack, pos, x, y)
    for rack in ("left", "right"):
        for i, (x, y) in enumerate(calib[rack], start=1):
            centers.append((rack, i, x, y))
    r = calib.get("slot_radius", 25)
    for v in vials:
        cx, cy = v["centroid"]
        best = min(centers, key=lambda c: (c[2] - cx) ** 2 + (c[3] - cy) ** 2)
        dist = ((best[2] - cx) ** 2 + (best[3] - cy) ** 2) ** 0.5
        v["rack"], v["position"] = (best[0], best[1]) if dist < r * 2.5 else (None, None)
    return vials


def annotate(img, vials, calib):
    out = img.copy()
    if calib:
        for rack in ("left", "right"):
            for i, (x, y) in enumerate(calib[rack], start=1):
                cv2.circle(out, (int(x), int(y)), 4, (200, 200, 200), -1)
                cv2.putText(out, f"{rack[0].upper()}{i}", (int(x) + 5, int(y) - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
    for v in vials:
        x, y, w, h = v["bbox"]
        bgr = DRAW_BGR.get(v["color"], (255, 255, 255))
        cv2.rectangle(out, (x, y), (x + w, y + h), bgr, 2)
        label = v["color"]
        if v.get("rack"):
            label += f" {v['rack']}{v['position']}"
        cv2.putText(out, label, (x, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, bgr, 2)
    return out


def _write_calib(clicks):
    """clicks = [L_pos1, L_pos6, R_pos1, R_pos6] -> interpolate 6 each, save JSON."""
    def interp(p1, p6):
        xs = np.linspace(p1[0], p6[0], N_SLOTS)
        ys = np.linspace(p1[1], p6[1], N_SLOTS)
        return [[float(x), float(y)] for x, y in zip(xs, ys)]
    left, right = interp(clicks[0], clicks[1]), interp(clicks[2], clicks[3])
    spacing = ((clicks[1][0] - clicks[0][0]) ** 2 + (clicks[1][1] - clicks[0][1]) ** 2) ** 0.5 / (N_SLOTS - 1)
    calib = {"rotate": "ccw90", "left": left, "right": right, "slot_radius": round(spacing * 0.5, 1)}
    CALIB_PATH.write_text(json.dumps(calib, indent=2))
    print(f"Saved calibration -> {CALIB_PATH}")
    return calib


def save_grid():
    """Save the current frame with a labeled pixel-coordinate grid, for headless calibration."""
    img = fetch_top()
    h, w = img.shape[:2]
    for x in range(0, w, 40):
        cv2.line(img, (x, 0), (x, h), (0, 255, 0), 1)
        cv2.putText(img, str(x), (x + 1, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1)
    for y in range(0, h, 40):
        cv2.line(img, (0, y), (w, y), (0, 255, 0), 1)
        cv2.putText(img, str(y), (1, y + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1)
    path = "/tmp/slot_grid.jpg"
    cv2.imwrite(path, img)
    print(f"Grid image -> {path}\nOpen it, read the (x,y) of the 4 slot ends, then run:\n"
          "  ee/slot_reader.py --calibrate-coords \"Lx1,Ly1 Lx6,Ly6 Rx1,Ry6 Rx6,Ry6\"\n"
          "  (order: LEFT pos1, LEFT pos6, RIGHT pos1, RIGHT pos6)")


def calibrate_from_coords(spec: str):
    pts = [tuple(float(v) for v in p.split(",")) for p in spec.split()]
    if len(pts) != 4:
        raise SystemExit('need 4 points: "Lx1,Ly1 Lx6,Ly6 Rx1,Ry1 Rx6,Ry6"')
    _write_calib(pts)


def calibrate():
    img = fetch_top()
    clicks = []
    order = ["LEFT rack POSITION 1 (nearest arm / top)",
             "LEFT rack POSITION 6 (far end / bottom)",
             "RIGHT rack POSITION 1 (nearest arm / top)",
             "RIGHT rack POSITION 6 (far end / bottom)"]

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(clicks) < 4:
            clicks.append((x, y))
            print(f"  clicked {order[len(clicks) - 1]} -> ({x},{y})")

    win = "calibrate — click the 4 points in order (see terminal)"
    try:
        cv2.namedWindow(win)
        cv2.setMouseCallback(win, on_mouse)
    except cv2.error:
        print("This OpenCV build has NO GUI (headless). Use the no-GUI calibration:\n"
              "  ee/slot_reader.py --grid              # saves /tmp/slot_grid.jpg with coords\n"
              '  ee/slot_reader.py --calibrate-coords "Lx1,Ly1 Lx6,Ly6 Rx1,Ry1 Rx6,Ry6"')
        return
    print("Click, IN ORDER:")
    for o in order:
        print("  -", o)
    while True:
        disp = img.copy()
        for i, (x, y) in enumerate(clicks):
            cv2.circle(disp, (x, y), 5, (0, 0, 255), -1)
            cv2.putText(disp, str(i + 1), (x + 6, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        nxt = order[len(clicks)] if len(clicks) < 4 else "DONE — press any key to save"
        cv2.putText(disp, f"Next: {nxt}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.imshow(win, disp)
        if cv2.waitKey(20) != -1 and len(clicks) == 4:
            break
    cv2.destroyAllWindows()
    _write_calib(clicks)


def read(show: bool):
    img = fetch_top()
    calib = load_calib()
    vials = detect_vials(img)
    if calib:
        vials = assign_slots(vials, calib)
    else:
        print("(no calibration yet — showing vial boxes only; run --calibrate for slot numbers)")

    out = annotate(img, vials, calib)
    cv2.imwrite(OUT_PATH, out)

    # structured scene state
    state = {"left": {}, "right": {}, "unassigned": []}
    for v in vials:
        if v.get("rack"):
            state[v["rack"]][v["position"]] = v["color"]
        else:
            state["unassigned"].append(v["color"])
    print("SCENE:", json.dumps(state))
    for rack in ("left", "right"):
        filled = ", ".join(f"pos{p}={c}" for p, c in sorted(state[rack].items())) or "empty"
        print(f"  {rack} rack: {filled}")
    if state["unassigned"]:
        print(f"  unassigned vials (no nearby slot): {state['unassigned']}")
    print(f"Annotated image -> {OUT_PATH}")

    if show:
        try:
            cv2.imshow("slot read", out)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        except cv2.error:
            print(f"(no GUI in this OpenCV build — open the saved file instead: {OUT_PATH})")


def main():
    global SERVER
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=SERVER)
    ap.add_argument("--calibrate", action="store_true", help="GUI: click 4 slot centers (needs display)")
    ap.add_argument("--grid", action="store_true", help="headless: save a coord-grid image to read slot ends from")
    ap.add_argument("--calibrate-coords", default=None,
                    help='headless: 4 points "Lx1,Ly1 Lx6,Ly6 Rx1,Ry1 Rx6,Ry6"')
    ap.add_argument("--show", action="store_true", help="pop an OpenCV window with the result (needs display)")
    args = ap.parse_args()
    SERVER = args.server
    if args.grid:
        save_grid()
    elif args.calibrate_coords:
        calibrate_from_coords(args.calibrate_coords)
    elif args.calibrate:
        calibrate()
    else:
        read(args.show)


if __name__ == "__main__":
    main()
