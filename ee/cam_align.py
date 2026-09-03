#!/usr/bin/env python3
"""
Camera re-alignment helper — put a camera back where it was during recording.

WHY: π0 has a FROZEN vision backbone and places the vial at a *memorized visual
target*. If a camera gets nudged after recording, every placement shifts and the
vial lands in the wrong spot ("between the racks"). This tool measures how far the
CURRENT camera view has drifted from the ORIGINAL recording view and tells you
exactly how to nudge it back — then you re-run to confirm the drift shrank to ~0.

HOW IT WORKS (classical CV, reliable & quantitative):
  - ORB feature matching + RANSAC between the two screenshots. RANSAC locks onto the
    FIXED background (racks, table, base) and ignores moving vials.
  - Estimates the translation / rotation / zoom between them and prints plain
    instructions ("shift RIGHT ~40px, rotate CW 2.3°, zoom IN 4%").
  - Saves visuals: a red/green overlay (red = original, green = current; aligned
    => grey/yellow, no colour fringes) and a side-by-side.

WORKFLOW:
  1. Put your ORIGINAL recording screenshot (from Hugging Face / the rerun.io
     visualizer of your dataset) at REFERENCE_IMG below.
  2. Put a screenshot of your CURRENT camera feed at CURRENT_IMG (from the server
     dashboard's camera view, or `ee/cam_align.py --fetch cam_top` to grab it live).
  3. Run:  .venv/bin/python ee/cam_align.py
  4. Adjust the camera as instructed, take a NEW current screenshot, re-run.
     Repeat until it prints "ALIGNED".

Both screenshots must be the SAME camera in the SAME orientation. Differing image
sizes are fine — the current image is resized to the reference's dimensions.
"""

import argparse
import base64
import json
import os
import urllib.request

import cv2
import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
#  EDIT THESE TWO PATHS.  Swap them to align a different camera (top/wrist/side).
# ─────────────────────────────────────────────────────────────────────────────
# REFERENCE = the ORIGINAL view from your recordings (HF dataset / rerun.io screenshot).
# Swap _top_ for _wrist_ / _side_ to align a different camera.
REFERENCE_IMG = "ee/align/old_camera_reference_top_FULL.png"   # original recording screenshot
# CURRENT = a screenshot of the camera RIGHT NOW (or use --fetch cam_top to grab it live).
CURRENT_IMG = "ee/align/current_cam_top.png"          # written by --fetch, or drop your own
# ─────────────────────────────────────────────────────────────────────────────

SERVER = "http://192.168.123.198:8000"   # used only by --fetch
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
VLM_MODEL = os.environ.get("VLM_MODEL", "gemma3:27b")

# "aligned enough" thresholds (resolution-independent where possible)
TOL_TRANS_FRAC = 0.012   # 1.2% of width/height
TOL_ROT_DEG = 0.8
TOL_SCALE = 0.025        # 2.5% zoom


def fetch_current(camera: str, server: str, out_path: str) -> str:
    """Grab the current frame for `camera` from the warm server's /observe -> save it."""
    d = json.load(urllib.request.urlopen(f"{server}/observe", timeout=30))["images"]
    if camera not in d:
        raise SystemExit(f"camera {camera!r} not in /observe (have: {list(d)})")
    buf = np.frombuffer(base64.b64decode(d[camera]), np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    cv2.imwrite(out_path, img)
    print(f"Saved current {camera} -> {out_path}")
    return out_path


def load(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"could not read image: {path}\n"
                         "  (put the screenshot there, or check the path at the top of this file)")
    return img


def estimate_transform(ref: np.ndarray, cur: np.ndarray) -> dict:
    """ORB + RANSAC partial-affine mapping CURRENT onto REFERENCE.
    Returns translation (px, in reference pixels), rotation (deg), scale, and inlier count.
    """
    g_ref = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
    g_cur = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY)

    orb = cv2.ORB_create(nfeatures=5000)
    k_ref, d_ref = orb.detectAndCompute(g_ref, None)
    k_cur, d_cur = orb.detectAndCompute(g_cur, None)
    if d_ref is None or d_cur is None or len(k_ref) < 10 or len(k_cur) < 10:
        return {"ok": False, "reason": "too few features (blurry / very different images?)"}

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = sorted(bf.match(d_cur, d_ref), key=lambda m: m.distance)
    if len(matches) < 12:
        return {"ok": False, "reason": f"only {len(matches)} matches (need >=12)"}

    src = np.float32([k_cur[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)  # current
    dst = np.float32([k_ref[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)  # reference
    M, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                             ransacReprojThreshold=3.0)
    if M is None:
        return {"ok": False, "reason": "RANSAC failed to find a transform"}

    n_in = int(inliers.sum()) if inliers is not None else 0
    scale = float(np.hypot(M[0, 0], M[0, 1]))
    rot = float(np.degrees(np.arctan2(M[1, 0], M[0, 0])))
    tx, ty = float(M[0, 2]), float(M[1, 2])
    return {"ok": True, "M": M, "tx": tx, "ty": ty, "rot": rot, "scale": scale,
            "inliers": n_in, "matches": len(matches)}


def instructions(t: dict, w: int, h: int) -> list[str]:
    """Human guidance to make the CURRENT view match the REFERENCE.
    Directions are in IMAGE space — the reliable loop is: adjust, re-screenshot,
    re-run, watch the numbers shrink toward 0."""
    out = []
    fx, fy = t["tx"] / w, t["ty"] / h

    aligned = (abs(fx) < TOL_TRANS_FRAC and abs(fy) < TOL_TRANS_FRAC
               and abs(t["rot"]) < TOL_ROT_DEG and abs(t["scale"] - 1) < TOL_SCALE)
    if aligned:
        out.append("✅ ALIGNED — within tolerance. The camera is back where it was. Done.")
        return out

    # translation: positive tx means current content must move RIGHT to match reference
    if abs(fx) >= TOL_TRANS_FRAC:
        d = "RIGHT" if t["tx"] > 0 else "LEFT"
        out.append(f"• Shift the view {d} by ~{abs(t['tx']):.0f}px "
                   f"({abs(fx)*100:.1f}% of width)  → pan the camera so the scene moves {d}.")
    if abs(fy) >= TOL_TRANS_FRAC:
        d = "DOWN" if t["ty"] > 0 else "UP"
        out.append(f"• Shift the view {d} by ~{abs(t['ty']):.0f}px "
                   f"({abs(fy)*100:.1f}% of height) → tilt the camera so the scene moves {d}.")
    if abs(t["rot"]) >= TOL_ROT_DEG:
        d = "counter-clockwise (CCW)" if t["rot"] > 0 else "clockwise (CW)"
        out.append(f"• Rotate the camera {d} by ~{abs(t['rot']):.1f}°.")
    if abs(t["scale"] - 1) >= TOL_SCALE:
        pct = (t["scale"] - 1) * 100
        if t["scale"] > 1:   # current is zoomed OUT vs ref -> enlarge -> move closer
            out.append(f"• Zoom IN ~{pct:.1f}% (move the camera CLOSER to the scene).")
        else:
            out.append(f"• Zoom OUT ~{abs(pct):.1f}% (move the camera FARTHER from the scene).")
    out.append("Then take a NEW current screenshot and re-run — the offsets should shrink toward 0.")
    return out


def make_visuals(ref: np.ndarray, cur: np.ndarray, t: dict) -> None:
    """Red/green overlay (red=reference, green=current) + side-by-side + the
    current image warped to alignment (so you can preview a perfect match)."""
    h, w = ref.shape[:2]
    g_ref = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
    g_cur = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY)

    def grid(img):
        img = img.copy()
        for x in range(0, w, w // 8):
            cv2.line(img, (x, 0), (x, h), (60, 60, 60), 1)
        for y in range(0, h, h // 6):
            cv2.line(img, (0, y), (w, y), (60, 60, 60), 1)
        return img

    # overlay BEFORE alignment: red = reference, green = current. Colour fringes = drift.
    overlay = np.zeros((h, w, 3), np.uint8)
    overlay[:, :, 2] = g_ref   # red channel
    overlay[:, :, 1] = g_cur   # green channel
    cv2.imwrite("/tmp/cam_align_overlay.jpg", grid(overlay))

    # side by side
    sbs = np.hstack([grid(ref), grid(cur)])
    cv2.putText(sbs, "REFERENCE (target)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(sbs, "CURRENT", (w + 10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    cv2.imwrite("/tmp/cam_align_sidebyside.jpg", sbs)

    # preview: warp current into the reference frame; overlay should go grey if model is right
    if t.get("ok"):
        warped = cv2.warpAffine(cur, t["M"], (w, h))
        g_warp = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        aligned_overlay = np.zeros((h, w, 3), np.uint8)
        aligned_overlay[:, :, 2] = g_ref
        aligned_overlay[:, :, 1] = g_warp
        cv2.imwrite("/tmp/cam_align_overlay_after.jpg", grid(aligned_overlay))

    print("Saved visuals:")
    print("  /tmp/cam_align_overlay.jpg        (red=reference, green=current; colour fringe = drift)")
    print("  /tmp/cam_align_sidebyside.jpg     (the two screenshots side by side)")
    if t.get("ok"):
        print("  /tmp/cam_align_overlay_after.jpg  (current digitally aligned — your TARGET look)")


def ask_vlm(ref_path: str, cur_path: str) -> None:
    """OPTIONAL second opinion from a local VLM (Ollama). The CV numbers above are
    the source of truth; this is just a sanity check / plain-language description."""
    def b64(p):
        return base64.b64encode(open(p, "rb").read()).decode("ascii")
    payload = {
        "model": VLM_MODEL,
        "messages": [{
            "role": "user",
            "content": ("Image 1 is the TARGET camera view. Image 2 is the CURRENT camera view "
                        "of the same fixed scene after the camera was bumped. In one or two short "
                        "sentences, how should I physically move the camera (left/right/up/down/"
                        "rotate/closer/farther) so CURRENT matches TARGET?"),
            "images": [b64(ref_path), b64(cur_path)],
        }],
        "stream": False,
        "options": {"temperature": 0},
    }
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            print("\nVLM second opinion:", json.loads(r.read())["message"]["content"].strip())
    except Exception as e:  # noqa: BLE001
        print(f"\n(VLM optional step failed: {e!r} — rely on the CV numbers above)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", default=REFERENCE_IMG)
    ap.add_argument("--current", default=CURRENT_IMG)
    ap.add_argument("--fetch", default=None, metavar="CAM",
                    help="grab the current frame live from the server (e.g. cam_top) and use it as --current")
    ap.add_argument("--server", default=SERVER)
    ap.add_argument("--vlm", action="store_true", help="also ask a local VLM for a plain-language opinion")
    args = ap.parse_args()

    cur_path = args.current
    if args.fetch:
        cur_path = fetch_current(args.fetch, args.server, args.current)

    ref = load(args.reference)
    cur = load(cur_path)
    h, w = ref.shape[:2]
    if cur.shape[:2] != (h, w):
        if abs((cur.shape[1] / cur.shape[0]) - (w / h)) > 0.05:
            print("⚠ aspect ratios differ — resizing anyway, but try to screenshot the same crop.")
        cur = cv2.resize(cur, (w, h))

    print(f"Reference: {args.reference}  ({w}x{h})")
    print(f"Current:   {cur_path}\n")

    t = estimate_transform(ref, cur)
    if not t["ok"]:
        print(f"Could not estimate the shift: {t['reason']}")
        print("Tips: same camera, similar lighting, include the fixed racks/table in both shots.")
        make_visuals(ref, cur, t)
        return

    print(f"Measured drift (current vs reference), from {t['inliers']}/{t['matches']} matched points:")
    print(f"  translation: dx={t['tx']:+.0f}px  dy={t['ty']:+.0f}px")
    print(f"  rotation:    {t['rot']:+.2f}°")
    print(f"  zoom/scale:  {t['scale']:.3f}  ({(t['scale']-1)*100:+.1f}%)\n")
    print("WHAT TO DO:")
    for line in instructions(t, w, h):
        print("  " + line)
    print()
    make_visuals(ref, cur, t)

    if args.vlm:
        ask_vlm(args.reference, cur_path)


if __name__ == "__main__":
    main()
