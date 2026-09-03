#!/usr/bin/env python3
"""
Robometer CONTINUOUS SIDECAR OBSERVER (workstation).

Robometer-4B watches π0.5 sort vials and produces a LIVE progress/success timeline. It is a
pure observer: it only READS Thor /state + /observe and NEVER feeds anything back into π0.5.

  - an OBSERVER thread polls Thor /state (~4Hz): when phase==execute it grabs the side cam and
    marks an episode; when phase leaves execute it closes the episode (control-side boundary).
    This means it graphs EVERY run — this dashboard's buttons OR the operator's cv_run VIAL SORT.
  - a SCORER thread scores the episode-so-far every ~1.2s -> appends (t, progress, success) to a
    live series, and runs a Robometer completion-detector (progress>=P & success>=S) -> a SECOND
    (different-coloured, toggleable) episode marker, so you can SEE the gap between "π0.5 finished"
    and "Robometer thinks it finished".
  - every episode is RECORDED (side-cam mp4 + time-synced series.json under ee/robometer_runs/) so
    the chart can be replayed 1-to-1 with the video.

/run and /vialsort are TRIGGER-ONLY (they issue Thor home/execute/release; the observer does the
scoring). Robometer stays on the WS (Thor is aarch64 + would share π0.5's GPU). fps=3 scoring,
success read at PEAK. See ee/ROBOMETER_VALIDATION.md.

Run (robometer venv):
    ee/robometer/.venv/bin/python ee/robometer_server.py --host 0.0.0.0 --port 8010 \
        --server http://192.168.123.152:8000
"""
from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from assess_robometer import RobometerScorer, load_video_frames  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import requests  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, File, Form, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse  # noqa: E402

SCORER: RobometerScorer | None = None
THRESHOLD = 0.5
THOR = "http://192.168.123.152:8000"
RUNS_CSV = Path(__file__).parent / "robometer_runs.csv"
RUNS_DIR = Path(__file__).parent / "robometer_runs"
RUNS_3FEED_DIR = Path(__file__).parent / "robometer_3feed"   # flat dir: <timestamp>_3feed.mp4 (all 3 feeds)
SCORE_LOCK = threading.Lock()         # serialize GPU inference
OBS_LOCK = threading.Lock()           # guards the live series + current episode
RUN_LOCK = threading.Lock()           # serialize robot triggers
SESSION = {"n": 0, "ok": 0}
BIN_WORDS = ("bin", "trash", "waste", "rubbish", "discard")
DUR_BIN, DUR_RACK, HOME_DUR = 38.0, 42.0, 4.0
TRAIL_BIN, TRAIL_RACK = 3.5, 1.0     # keep observing this long past 'execute' — bin-drop happens in the release
# Robometer completion-detector (tuned for OUR domain, where progress peaks ~0.8 & success ~0.5;
# the doc's 0.85/0.80 never fire here). These are diagnostic, not ground truth.
P_COMPLETE, S_COMPLETE, N_CONSEC, P_RESET = 0.70, 0.50, 2, 0.30
SERIES_CAP = 4000                     # rolling live-series length (~20 min at 0.8 pts/s)
START_T = time.time()

VIAL_SORT_STEPS = [
    {"kind": "home", "home_dur": 4.0},
    {"kind": "execute", "task": "Move the vial from position 4 of the left rack to the bin.", "duration": 33.0},
    {"kind": "release"},
    {"kind": "home", "home_dur": 4.0},
    {"kind": "execute", "task": "Move the vial from position 3 of the right rack to slot 3 of the left rack.", "duration": 38.0},
]

# live observer state (guarded by OBS_LOCK)
OBS = {
    "reachable": False, "phase": "idle", "task": "",
    "t": deque(maxlen=SERIES_CAP), "progress": deque(maxlen=SERIES_CAP), "success": deque(maxlen=SERIES_CAP),
    "markers": deque(maxlen=400),   # {t, kind:'ctrl'|'rbm', label}
    "cur": None,                     # current live progress/success
    "episodes": deque(maxlen=200),   # closed-episode summaries
}
EP: dict | None = None               # the in-progress episode (frames + relative series), guarded by OBS_LOCK
LATEST = {"images": {}, "ts": 0.0, "reachable": False}   # continuously-refreshed camera cache (smooth feed)
CAPTURING = False        # set by the observer during execute+trail; the cam loop records frames while True

app = FastAPI(title="robometer-observer")


# ── Thor proxy (READ-ONLY for observation; POST only for the trigger buttons) ────────
def thor_get(path: str, timeout: float = 8.0) -> dict:
    return requests.get(f"{THOR}{path}", timeout=timeout).json()


def thor_post(path: str, payload: dict, timeout: float = 600.0) -> dict:
    return requests.post(f"{THOR}{path}", json=payload, timeout=timeout).json()


def _fetch_thor_clip(dst_dir: Path):
    """Pull Thor's native full-rate 3-feed clip (recorded ON the robot, no /observe frame-skip) plus its
    timing meta. Returns (raw_mp4_path, meta) or (None, None). Retries once — Thor finalizes the file a beat
    after execute+release, and our episode close (post-trail) normally lands after that."""
    for _ in range(2):
        try:
            info = requests.get(f"{THOR}/last_clip_info", timeout=5).json()
            if isinstance(info, dict) and "n_frames" in info:
                r = requests.get(f"{THOR}/last_clip", timeout=40)
                if r.status_code == 200 and r.content:
                    raw = dst_dir / "thor_src.mp4"
                    raw.write_bytes(r.content)
                    return raw, info
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.6)
    return None, None


def _is_bin(task: str) -> bool:
    return any(w in (task or "").lower() for w in BIN_WORDS)


def robometer_prompt(task: str) -> str:
    """π0.5's position grammar ('slot 6 of the right rack') is un-groundable for Robometer, which was
    trained on simple appearance-based tasks. Translate to a plain, visually-verifiable description and
    DROP the slot/position indices. π0.5 still gets its own original prompt; only Robometer's differs."""
    if _is_bin(task):
        return "Pick up the vial and put it in the bin."
    return "Pick up the vial and place it in the tube rack."


def _sidecam(obs: dict) -> np.ndarray | None:
    imgs = (obs or {}).get("images", {})
    key = next((k for k in imgs if "side" in k.lower()), None) or next(iter(imgs), None)
    if not key:
        return None
    try:
        buf = np.frombuffer(base64.b64decode(imgs[key]), dtype=np.uint8)
        bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB) if bgr is not None else None
    except Exception:  # noqa: BLE001
        return None


def _allcams(imgs: dict) -> dict | None:
    """Decode all three cams (top/wrist/side) from a cached /observe images dict, for the composite replay."""
    out = {}
    for cam in ("top", "wrist", "side"):
        key = next((k for k in imgs if cam in k.lower()), None)
        if key:
            try:
                buf = np.frombuffer(base64.b64decode(imgs[key]), dtype=np.uint8)
                bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                if bgr is not None:
                    out[cam] = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            except Exception:  # noqa: BLE001
                pass
    return out or None


def _subsample(frames: list, cap: int = 64) -> np.ndarray:
    if len(frames) > cap:
        idx = np.linspace(0, len(frames) - 1, cap).astype(int)
        frames = [frames[i] for i in idx]
    return np.stack(frames).astype(np.uint8)


def _now() -> float:
    return time.time() - START_T


# ── Episode recording ────────────────────────────────────────────────────────────────
def _log_csv(task: str, ep_id: str, res: dict) -> None:
    new = not RUNS_CSV.exists()
    with open(RUNS_CSV, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["timestamp", "id", "prompt", "rbm_success_peak", "rbm_verdict", "outcome"])
        w.writerow([dt.datetime.now().isoformat(timespec="seconds"), ep_id, task,
                    res.get("peak_success"), res.get("verdict"), ""])


def _save_episode(ep: dict) -> dict:
    """Write a COMPOSITE video (side | top | wrist, H.264) + series.json (episode-relative time, 1-to-1
    with the video). ep['frames'] is a list of (trel, {top,wrist,side})."""
    ep_id = ep["id"]
    d = RUNS_DIR / ep_id
    d.mkdir(parents=True, exist_ok=True)
    frames = ep["frames"]
    fps = None
    video_src = None

    # 1) PREFER Thor's native full-rate 3-feed clip (recorded ON the robot — every control step, no skip).
    #    Thor writes it at a fixed nominal fps, so retime to the real elapsed duration -> chart stays 1-to-1.
    raw, meta = _fetch_thor_clip(d)
    if raw is not None:
        try:
            n = max(int(meta.get("n_frames", 0)), 1)
            el = max(float(meta.get("elapsed", 0.0)), 0.001)
            nom = float(meta.get("nominal_fps", 30.0))
            factor = max(nom * el / n, 0.01)          # setpts multiplier -> real-time playback
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
                   "-filter:v", f"setpts={factor:.5f}*PTS",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(d / "video.mp4")]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180, check=True)
            fps = round(n / el, 2)
            video_src = "thor-native"
        except Exception:  # noqa: BLE001
            video_src = None
        finally:
            try:
                raw.unlink()
            except Exception:  # noqa: BLE001
                pass

    # 2) FALLBACK: composite from the WS-captured /observe frames (lower fps than Thor's native clip).
    if video_src is None:
        def _composite(fr: dict):
            order = [c for c in ("side", "top", "wrist") if fr.get(c) is not None]
            if not order:
                return None
            h = 260
            tiles = [cv2.resize(fr[c], (int(fr[c].shape[1] * h / fr[c].shape[0]), h)) for c in order]
            return np.hstack(tiles)

        comps = [(t, _composite(fr)) for t, fr in frames]
        comps = [(t, c) for t, c in comps if c is not None]
        if len(comps) >= 2:
            span = max(comps[-1][0] - comps[0][0], 0.1)
            fps = min(max(len(comps) / span, 1.0), 30.0)
            H, W = comps[0][1].shape[:2]
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                   "-s", f"{W}x{H}", "-r", f"{fps:.3f}", "-i", "-",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(d / "video.mp4")]
            try:
                p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                for _, c in comps:
                    p.stdin.write(np.ascontiguousarray(c, dtype=np.uint8).tobytes())
                p.stdin.close()
                p.wait(timeout=120)
                video_src = "ws-observe"
            except Exception:  # noqa: BLE001
                fps = None

    if (d / "video.mp4").exists():            # drop the final video into the flat, timestamp-named dir
        try:
            flat = RUNS_3FEED_DIR / f"{ep_id}_3feed.mp4"
            if flat.exists():
                flat.unlink()
            flat.hardlink_to(d / "video.mp4")
        except Exception:  # noqa: BLE001
            pass
    peak_p = max(ep["progress"]) if ep["progress"] else None
    peak_s = max(ep["success"]) if ep["success"] else None
    verdict = int((peak_s or 0.0) >= THRESHOLD) if peak_s is not None else None
    series = {
        "id": ep_id, "task": ep["task"], "rbm_prompt": robometer_prompt(ep["task"]),
        "duration": round(ep.get("dur") or 0.0, 2), "fps": fps, "video_src": video_src, "cams": "side | top | wrist",
        "t": [round(x, 3) for x in ep["t"]], "progress": ep["progress"], "success": ep["success"],
        "ctrl_end": ep.get("ctrl_end"), "rbm_end": ep.get("rbm_end"),
        "peak_progress": peak_p, "peak_success": peak_s, "verdict": verdict,
        "threshold": THRESHOLD, "p_complete": P_COMPLETE, "s_complete": S_COMPLETE,
    }
    (d / "series.json").write_text(json.dumps(series))
    res = {"peak_success": peak_s, "peak_progress": peak_p, "verdict": verdict}
    _log_csv(ep["task"], ep_id, res)
    if verdict is not None:
        SESSION["n"] += 1
        SESSION["ok"] += int(verdict)
    return {"id": ep_id, "task": ep["task"], "verdict": verdict,
            "peak_success": peak_s, "peak_progress": peak_p}


# ── Camera cache + observer + scorer threads ──────────────────────────────────────────
def _cam_loop():
    """Continuously cache Thor /observe so the browser feed reads a local cache and never waits on a
    per-request round-trip — fixes the stutter when Thor is busy (e.g. the bin-release)."""
    while True:
        try:
            imgs = thor_get("/observe", timeout=5).get("images", {})
            if imgs:                       # keep last-good frames on an empty/hiccup response (no blanking)
                LATEST["images"] = imgs
                LATEST["ts"] = _now()
                if CAPTURING:              # record at the /observe rate (not the 4Hz observer) -> better fps
                    fr = _allcams(imgs)
                    if fr and fr.get("side") is not None:
                        with OBS_LOCK:
                            ep = EP
                            if ep is not None:
                                ep["frames"].append((_now() - ep["start"], fr))
            LATEST["reachable"] = True
        except Exception:  # noqa: BLE001
            LATEST["reachable"] = False
        time.sleep(0.04 if CAPTURING else 0.1)


def _observer_loop():
    """~4Hz: track Thor phase, open/close episodes, toggle CAPTURING (frame recording runs in the fast cam loop)."""
    global EP, CAPTURING
    while True:
        t = _now()
        try:
            st = thor_get("/state", timeout=4)
            reachable, phase = True, st.get("phase", "idle")
            task = st.get("task") or ""
        except Exception:  # noqa: BLE001
            reachable, phase, task = False, "unreachable", ""
        executing = (phase == "execute")
        with OBS_LOCK:
            OBS["reachable"], OBS["phase"] = reachable, phase
            if executing and EP is None:                         # episode START
                EP = {"id": dt.datetime.now().strftime("%Y%m%d-%H%M%S"), "task": task or OBS["task"],
                      "start": t, "frames": [], "t": [], "progress": [], "success": [],
                      "ctrl_end": None, "rbm_end": None, "exec_end": None, "trail_until": None,
                      "armed": True, "consec": 0}
                OBS["task"] = EP["task"]
            if executing and EP is not None:
                if task:
                    EP["task"] = task
                    OBS["task"] = task
                EP["trail_until"] = None                         # cancel any trail while still executing
                EP["exec_end"] = None
            ep = EP
        capture = close = False
        if ep is not None:
            if executing:
                capture = True
            else:
                with OBS_LOCK:
                    if EP is ep:
                        if ep["trail_until"] is None:            # first tick past execute: π0.5 end + start trail
                            ep["exec_end"] = round(t - ep["start"], 3)
                            OBS["markers"].append({"t": round(t, 3), "kind": "ctrl", "label": (ep["task"] or "")[:30]})
                            ep["trail_until"] = t + (TRAIL_BIN if _is_bin(ep["task"]) else TRAIL_RACK)
                        capture = t < ep["trail_until"]
                        close = t >= ep["trail_until"]
        CAPTURING = bool(capture and ep is not None)              # cam loop records frames at the /observe rate
        if close and ep is not None:                              # episode END (after the bin-drop trail)
            with OBS_LOCK:
                ep["dur"] = t - ep["start"]
                ep["ctrl_end"] = ep.get("exec_end") or round(ep["dur"], 3)
                EP = None
            summ = _save_episode(ep)
            with OBS_LOCK:
                OBS["episodes"].append(summ)
                OBS["cur"] = None
        time.sleep(0.25)


def _scorer_loop():
    """~every 1.2s: score the episode-so-far, append (t,progress,success), run completion-detector."""
    last = 0.0
    while True:
        time.sleep(0.2)
        if _now() - last < 1.2:
            continue
        with OBS_LOCK:
            ep = EP
            frames = list(ep["frames"]) if ep else []
        side = [fr["side"] for _, fr in frames if isinstance(fr, dict) and fr.get("side") is not None]
        if ep is None or len(side) < 6:
            continue
        last = _now()
        rbm_task = robometer_prompt(ep["task"])
        try:
            with SCORE_LOCK:
                r = SCORER.score(_subsample(side), rbm_task)
        except Exception:  # noqa: BLE001
            continue
        prog = float(r["progress"][-1]) if r.get("progress") else None
        succ = float(r["success"][-1]) if r.get("success") else None
        if prog is None:
            continue
        t = _now()
        with OBS_LOCK:
            if EP is not ep:      # episode closed while we scored
                continue
            trel = t - ep["start"]
            ep["t"].append(trel); ep["progress"].append(round(prog, 4)); ep["success"].append(round(succ or 0.0, 4))
            OBS["t"].append(round(t, 3)); OBS["progress"].append(round(prog, 4)); OBS["success"].append(round(succ or 0.0, 4))
            OBS["cur"] = {"task": ep["task"], "rbm_prompt": rbm_task, "progress": round(prog, 4),
                          "success": round(succ or 0.0, 4), "n_frames": len(frames),
                          "success_peak": round(max(ep["success"]), 4) if ep["success"] else round(succ or 0.0, 4),
                          "progress_peak": round(max(ep["progress"]), 4) if ep["progress"] else round(prog, 4)}
            # Robometer completion-detector (armed/re-arm)
            if ep["armed"] and succ is not None and prog >= P_COMPLETE and succ >= S_COMPLETE:
                ep["consec"] += 1
                if ep["consec"] >= N_CONSEC:
                    ep["rbm_end"] = round(trel, 3)
                    OBS["markers"].append({"t": round(t, 3), "kind": "rbm", "label": (ep["task"] or "")[:30]})
                    ep["armed"] = False
            elif prog < P_RESET:
                ep["armed"], ep["consec"] = True, 0
            else:
                ep["consec"] = 0


# ── Endpoints ──────────────────────────────────────────────────────────────────────
@app.get("/health")
def health() -> dict:
    return {"ok": SCORER is not None, "model": "robometer/Robometer-4B", "threshold": THRESHOLD,
            "device": str(SCORER.device) if SCORER else None, "thor": THOR}


@app.get("/live")
def live() -> dict:
    """Camera frames from the continuously-refreshed cache (never waits on Thor -> smooth feed)."""
    return {"phase": OBS.get("phase", "idle"), "images": LATEST["images"],
            "reachable": OBS.get("reachable", False) or LATEST["reachable"]}


@app.get("/live_series")
def live_series() -> dict:
    with OBS_LOCK:
        return {"reachable": OBS["reachable"], "phase": OBS["phase"], "cur": OBS["cur"],
                "t": list(OBS["t"]), "progress": list(OBS["progress"]), "success": list(OBS["success"]),
                "markers": list(OBS["markers"]), "now": round(_now(), 3),
                "p_complete": P_COMPLETE, "s_complete": S_COMPLETE}


@app.get("/stats")
def stats() -> dict:
    n = ok = 0
    recent = []
    if RUNS_CSV.exists():
        rows = list(csv.DictReader(open(RUNS_CSV)))
        for row in rows:
            v = row.get("rbm_verdict")
            if v in (None, ""):
                continue
            n += 1
            ok += int(float(v))
        for row in rows[-8:][::-1]:
            recent.append({"task": row.get("prompt", ""), "verdict": row.get("rbm_verdict"),
                           "peak": row.get("rbm_success_peak")})
    return {"alltime": {"n": n, "ok": ok, "fail": n - ok, "fail_pct": (100 * (n - ok) / n) if n else None},
            "session": {"n": SESSION["n"], "ok": SESSION["ok"], "fail": SESSION["n"] - SESSION["ok"],
                        "fail_pct": (100 * (SESSION["n"] - SESSION["ok"]) / SESSION["n"]) if SESSION["n"] else None},
            "recent": recent}


@app.get("/runs")
def runs() -> dict:
    out = []
    if RUNS_DIR.exists():
        for d in sorted(RUNS_DIR.iterdir(), reverse=True):
            sj = d / "series.json"
            if sj.is_file():
                try:
                    s = json.loads(sj.read_text())
                    out.append({"id": s["id"], "task": s.get("task", ""), "verdict": s.get("verdict"),
                                "peak_success": s.get("peak_success"), "duration": s.get("duration"),
                                "has_video": (d / "video.mp4").is_file()})
                except Exception:  # noqa: BLE001
                    pass
    return {"runs": out[:100]}


@app.get("/runs/{run_id}")
def run_series(run_id: str) -> dict:
    sj = RUNS_DIR / run_id / "series.json"
    if not sj.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return json.loads(sj.read_text())


@app.get("/runs/{run_id}/video")
def run_video(run_id: str):
    mp4 = RUNS_DIR / run_id / "video.mp4"
    if not mp4.is_file():
        return JSONResponse({"error": "no video"}, status_code=404)
    return FileResponse(str(mp4), media_type="video/mp4")


# ── Robot TRIGGERS (the observer does the scoring; these just drive Thor) ─────────────
@app.post("/run")
def run(payload: dict) -> dict:
    task = (payload or {}).get("task")
    if not task:
        return JSONResponse({"error": "task required"}, status_code=400)
    is_bin = _is_bin(task)
    duration = float(payload.get("duration") or (DUR_BIN if is_bin else DUR_RACK))
    home_dur = float(payload.get("home_dur", HOME_DUR))
    if not RUN_LOCK.acquire(blocking=False):
        return JSONResponse({"error": "a run is already in progress"}, status_code=409)
    try:
        try:
            thor_post("/home", {"duration": home_dur}, timeout=120)
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": f"home failed: {e!r}"}, status_code=502)
        stats_run = thor_post("/execute", {"task": task, "duration": duration}, timeout=duration + 120)
        if is_bin:
            try:
                thor_post("/release", {}, timeout=30)
            except Exception:  # noqa: BLE001
                pass
        try:
            thor_post("/home", {"duration": home_dur}, timeout=120)
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "stats": stats_run, "note": "scored live by the observer; see the timeline"}
    finally:
        RUN_LOCK.release()


@app.post("/vialsort")
def vialsort() -> dict:
    if not RUN_LOCK.acquire(blocking=False):
        return JSONResponse({"error": "a run is already in progress"}, status_code=409)
    try:
        for st in VIAL_SORT_STEPS:
            if st["kind"] == "home":
                try:
                    thor_post("/home", {"duration": st["home_dur"]}, timeout=120)
                except Exception:  # noqa: BLE001
                    pass
            elif st["kind"] == "release":
                try:
                    thor_post("/release", {}, timeout=30)
                except Exception:  # noqa: BLE001
                    pass
            else:
                thor_post("/execute", {"task": st["task"], "duration": st["duration"]}, timeout=st["duration"] + 120)
        return {"ok": True, "note": "demo done; each move scored live by the observer"}
    finally:
        RUN_LOCK.release()


@app.post("/home")
def home(payload: dict | None = None) -> dict:
    dur = float((payload or {}).get("duration", HOME_DUR))
    if not RUN_LOCK.acquire(blocking=False):
        return JSONResponse({"error": "busy"}, status_code=409)
    try:
        return thor_post("/home", {"duration": dur}, timeout=120)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": repr(e)}, status_code=502)
    finally:
        RUN_LOCK.release()


@app.post("/release")
def release() -> dict:
    try:
        return thor_post("/release", {}, timeout=30)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": repr(e)}, status_code=502)


@app.post("/stop")
def stop() -> dict:
    try:
        return thor_post("/stop", {}, timeout=10)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": repr(e)}, status_code=502)


@app.post("/score")
async def score(task: str = Form(...), file: UploadFile | None = File(None),
                path: str | None = Form(None), fps: float = Form(3.0), max_frames: int = Form(64)):
    """Manual: score an arbitrary clip (batch/testing). Returns progress+success arrays."""
    if SCORER is None:
        return JSONResponse({"error": "model not loaded"}, status_code=503)
    tmp = None
    try:
        if file is not None:
            t = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            t.write(await file.read()); t.flush(); t.close(); tmp = t.name; vid = tmp
        elif path:
            vid = path
        else:
            return JSONResponse({"error": "provide file or path"}, status_code=400)
        frames = load_video_frames(vid, fps=fps, max_frames=max_frames)
        with SCORE_LOCK:
            r = SCORER.score(frames, task)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": repr(e)}, status_code=500)
    finally:
        if tmp:
            try:
                Path(tmp).unlink()
            except OSError:
                pass
    peak = r.get("success_max")
    return {"task": task, "progress": r.get("progress"), "success": r.get("success"),
            "success_peak": peak, "verdict": int((peak or 0) >= THRESHOLD), "n_frames": len(r.get("progress") or [])}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return PAGE


PAGE = r"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Robometer</title>
<style>
 :root{--bg:#0a0d13;--card:#111722;--line:#1e2836;--mut:#7c8aa0;--txt:#e7eefc;--accent:#4c8dff;--green:#2ec17a;--blue:#48b3ff;--red:#ff5670;--amber:#f5b544;--violet:#a978ff}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.45 system-ui,Segoe UI,Roboto,sans-serif}
 header{display:flex;align-items:center;gap:14px;padding:12px 20px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5}
 header .dot{width:11px;height:11px;border-radius:50%;background:var(--green);box-shadow:0 0 10px var(--green)}
 header b{letter-spacing:.4px}
 .tabs{display:flex;gap:6px;margin-left:6px} .tab{padding:6px 14px;border-radius:9px;border:1px solid var(--line);background:#0b111b;color:var(--mut);cursor:pointer;font-weight:700}
 .tab.on{background:var(--accent);border-color:var(--accent);color:#04121a} header .thor{margin-left:auto;color:var(--mut);font-size:12px}
 main{padding:16px 20px}
 main.two{display:grid;grid-template-columns:1fr 360px;gap:16px;align-items:start;max-width:1500px;margin:0 auto}
 @media(max-width:900px){main.two{grid-template-columns:1fr}}
 .leftcol,.rightcol{display:flex;flex-direction:column;gap:16px;min-width:0}
 .rightcol{position:sticky;top:70px}
 .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}
 h3{margin:0 0 10px;font-size:12px;text-transform:uppercase;letter-spacing:.6px;color:var(--mut)}
 .fld{display:block;color:var(--mut);font-size:11.5px;margin:0 0 5px}
 .seg{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
 .seg button{flex:1;min-width:30px;padding:8px 0;border-radius:8px;border:1px solid var(--line);background:#0b111b;color:var(--mut);font-weight:700;cursor:pointer}
 .seg button.on{background:var(--accent);border-color:var(--accent);color:#04121a} .seg button:disabled{opacity:.3;cursor:not-allowed}
 input{width:100%;padding:10px;border-radius:9px;border:1px solid var(--line);background:#0b111b;color:var(--txt)}
 .cmdrow{display:flex;gap:8px;margin-top:6px} .cmdrow .task{flex:1} .cmdrow .num{width:74px}
 .actions{display:flex;flex-direction:column;gap:8px} .actions button{width:100%;padding:12px;border:0;border-radius:10px;font-weight:700;font-size:14px;cursor:pointer}
 .go{background:linear-gradient(90deg,var(--accent),var(--green));color:#04121a} .demo{background:linear-gradient(90deg,var(--violet),var(--accent));color:#fff}
 .ghost{background:#0b111b;border:1px solid var(--line);color:var(--txt)} .stop{background:#25161c;color:var(--red);border:1px solid var(--red)}
 .grip{display:flex;gap:8px} .grip button{flex:1}
 button:disabled{opacity:.5;cursor:not-allowed}
 .frow{display:flex;gap:14px;align-items:center;margin-top:12px;flex-wrap:wrap;font-size:12.5px;color:var(--mut)} .frow b{color:var(--txt);font-size:16px}
 .cams{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px} @media(max-width:560px){.cams{grid-template-columns:1fr}}
 .cam{position:relative;background:#05070c;border:1px solid var(--line);border-radius:10px;overflow:hidden}
 .cam img{display:block;width:100%;aspect-ratio:4/3;object-fit:cover;background:#05070c}
 .cam .tag{position:absolute;top:7px;left:7px;font-size:10.5px;font-weight:800;letter-spacing:.5px;background:rgba(5,7,12,.66);border:1px solid var(--line);padding:3px 7px;border-radius:6px;color:var(--mut)}
 .cam.scored .tag{color:var(--green);border-color:var(--green)}
 .phase{display:inline-flex;align-items:center;gap:8px;font-weight:700;text-transform:uppercase;font-size:11px;letter-spacing:.4px}
 .phase .orb{width:9px;height:9px;border-radius:50%;background:var(--mut)}
 .phase.execute .orb{background:var(--green);box-shadow:0 0 8px var(--green)} .phase.unreachable .orb{background:var(--red)} .phase.home .orb{background:var(--amber)}
 .chead{display:flex;align-items:flex-end;gap:22px;flex-wrap:wrap;margin-bottom:10px}
 .stat{font-size:12px;color:var(--mut)} .stat b{display:block;font-size:26px;line-height:1.1}
 .legend{display:flex;gap:16px;flex-wrap:wrap;margin-left:auto}
 .legend label{display:inline-flex;align-items:center;gap:7px;cursor:pointer;font-size:14px;font-weight:600;color:var(--txt)}
 .legend .sw{width:16px;height:16px;border-radius:4px;display:inline-block} .legend input{width:auto}
 canvas.chart{width:100%;height:300px;background:#0b111b;border:1px solid var(--line);border-radius:10px;display:block;cursor:crosshair}
 #note{color:var(--mut);font-size:12px;margin-top:10px}
 .replay{display:grid;grid-template-columns:240px 1fr;gap:14px} @media(max-width:760px){.replay{grid-template-columns:1fr}}
 .runlist{max-height:560px;overflow:auto;display:flex;flex-direction:column;gap:6px}
 .runlist .r{padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:#0b111b;cursor:pointer;font-size:12.5px}
 .runlist .r.on{border-color:var(--accent)} .runlist .r .v{float:right;font-weight:700}
 video{width:100%;border-radius:10px;background:#000;border:1px solid var(--line)}
</style></head><body>
<header><span class=dot></span><b>ROBOMETER</b>
  <div class=tabs><span class="tab on" id=tabLive onclick=showTab('live')>Live</span><span class=tab id=tabReplay onclick=showTab('replay')>Replay</span></div>
  <span class=thor id=thor></span></header>

<main id=liveView class=two>
  <div class=leftcol>
    <section class=card>
      <h3>Live cameras &nbsp;·&nbsp; <span style="color:var(--green)">side = scored</span>
        &nbsp;<span class="phase" id=phase><span class=orb></span><span id=phaseTxt>idle</span></span></h3>
      <div class=cams>
        <div class=cam><img id=cam_top alt=top><span class=tag>TOP</span></div>
        <div class=cam><img id=cam_wrist alt=wrist><span class=tag>WRIST</span></div>
        <div class="cam scored"><img id=cam_side alt=side><span class=tag>SIDE</span></div>
      </div>
    </section>
    <section class=card>
      <h3>Robometer — live progress / success vs time</h3>
      <div class=chead>
        <span class=stat>peak progress <b id=curP style="color:var(--green)">–</b></span>
        <span class=stat>peak success <b id=curS style="color:var(--blue)">–</b></span>
        <span class=stat style="align-self:center" id=rbmP></span>
        <div class=legend>
          <label><input type=checkbox id=tP checked><span class=sw style="background:var(--green)"></span>progress</label>
          <label><input type=checkbox id=tS checked><span class=sw style="background:var(--blue)"></span>success</label>
          <label><input type=checkbox id=tC checked><span class=sw style="background:var(--amber)"></span>π0.5 end</label>
          <label><input type=checkbox id=tR checked><span class=sw style="background:var(--violet)"></span>robometer end</label>
        </div>
      </div>
      <canvas class=chart id=liveChart></canvas>
    </section>
  </div>

  <div class=rightcol>
    <section class=card>
      <h3>Command</h3>
      <span class=fld>Source rack</span><div class=seg id=srcRack></div>
      <span class=fld>Source position <span style=opacity:.6>(1,3,4,6)</span></span><div class=seg id=srcPos></div>
      <span class=fld>Destination</span><div class=seg id=dstRack></div>
      <span class=fld>Dest slot <span style=opacity:.6>(1,3,6 · bin=none)</span></span><div class=seg id=dstPos></div>
      <input class=task id=task style="margin-top:4px">
      <div class=cmdrow><input class=num id=dur type=number value=42 title=duration><input class=num id=home type=number value=4 title=home><span style="flex:1;color:var(--mut);font-size:11px;align-self:center">dur / home (s)</span></div>
    </section>
    <section class=card>
      <h3>Actions</h3>
      <div class=actions>
        <button class=go id=go onclick=runCmd()>▶ Execute</button>
        <button class=demo id=vs onclick=vialSort()>🧪 VIAL SORT</button>
        <div class=grip><button class=ghost id=homeBtn onclick=goHome()>⌂ Home</button><button class=ghost onclick=openGrip()>✋ Open gripper</button></div>
        <button class=stop onclick=stopArm()>■ EMERGENCY STOP</button>
      </div>
      <div class=frow><span>fail — session <b id=sfail>–</b></span><span>all-time <b id=afail>–</b></span></div>
      <div id=recent style="margin-top:6px"></div>
      <div id=note></div>
    </section>
  </div>
</main>

<main id=replayView style="display:none">
  <section class=card>
    <h3>Replay — chart 1-to-1 with the video</h3>
    <div class=replay>
      <div class=runlist id=runlist></div>
      <div>
        <video id=vid controls></video>
        <div class=chead style="margin-top:10px">
          <span class=stat id=rlabel>pick a run →</span>
          <div class=legend>
            <label><input type=checkbox id=rP checked><span class=sw style="background:var(--green)"></span>progress</label>
            <label><input type=checkbox id=rS checked><span class=sw style="background:var(--blue)"></span>success</label>
            <label><input type=checkbox id=rC checked><span class=sw style="background:var(--amber)"></span>π0.5 end</label>
            <label><input type=checkbox id=rR checked><span class=sw style="background:var(--violet)"></span>robometer end</label>
          </div>
        </div>
        <canvas class=chart id=replayChart></canvas>
        <div id=note2 style="color:var(--mut);font-size:12px;margin-top:8px"></div>
      </div>
    </div>
  </section>
</main>

<script>
const $=s=>document.querySelector(s); let busy=false;
const CAMS=['cam_top','cam_wrist','cam_side'];
const COL={prog:'#2ec17a',succ:'#48b3ff',ctrl:'#f5b544',rbm:'#a978ff'};
function showTab(t){ $('#tabLive').classList.toggle('on',t==='live');$('#tabReplay').classList.toggle('on',t==='replay');
  $('#liveView').style.display=t==='live'?'':'none';$('#replayView').style.display=t==='replay'?'':'none';if(t==='replay')loadRuns(); }
function pct(v){return v==null?'–':Math.round(v*100)+'%';}

// ---------- canvas chart with DEFINED AXES ----------
function fit(cv){const r=cv.getBoundingClientRect();const dpr=window.devicePixelRatio||1;cv.width=r.width*dpr;cv.height=r.height*dpr;const c=cv.getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);return[c,r.width,r.height];}
function drawChart(cv,S,o){
  const [c,W,H]=fit(cv); const L=46,R=16,T=12,B=38; const t=S.t||[],pr=S.progress||[],su=S.success||[];
  c.clearRect(0,0,W,H);
  let tmin=o.tmin,tmax=o.tmax; if(tmin==null)tmin=t.length?t[0]:0; if(tmax==null)tmax=t.length?t[t.length-1]:1; if(tmax-tmin<1)tmax=tmin+1;
  const X=v=>L+(v-tmin)/(tmax-tmin)*(W-L-R); const Y=v=>T+(1-v)*(H-T-B);
  // y gridlines + labels (0..1)
  c.font='11px system-ui';
  [0,0.25,0.5,0.75,1].forEach(g=>{ c.strokeStyle='#182234'; c.beginPath();c.moveTo(L,Y(g));c.lineTo(W-R,Y(g));c.stroke(); c.fillStyle='#8c9ab0'; c.fillText(g.toFixed(2),8,Y(g)+4); });
  // axis lines
  c.strokeStyle='#33425a'; c.lineWidth=1.2; c.beginPath();c.moveTo(L,T);c.lineTo(L,H-B);c.lineTo(W-R,H-B);c.stroke();
  // x ticks (time in s)
  c.fillStyle='#8c9ab0';
  for(let k=0;k<=5;k++){ const tv=tmin+(tmax-tmin)*k/5,x=X(tv); c.strokeStyle='#33425a';c.beginPath();c.moveTo(x,H-B);c.lineTo(x,H-B+4);c.stroke(); c.fillText(tv.toFixed(0),x-6,H-B+17); }
  c.fillText('time (s)',(L+W-R)/2-22,H-6);
  c.save();c.translate(13,(T+(H-B))/2+34);c.rotate(-Math.PI/2);c.fillText('progress / success',0,0);c.restore();
  // markers
  (S.markers||[]).forEach(m=>{ if(m.kind==='ctrl'&&!o.showC)return; if(m.kind==='rbm'&&!o.showR)return; const x=X(m.t); if(x<L-1||x>W-R+1)return;
    c.strokeStyle=m.kind==='ctrl'?COL.ctrl:COL.rbm;c.setLineDash([6,4]);c.lineWidth=1.6;c.beginPath();c.moveTo(x,T);c.lineTo(x,H-B);c.stroke();c.setLineDash([]); });
  function line(arr,col){c.strokeStyle=col;c.lineWidth=2.2;c.beginPath();let s=false;for(let i=0;i<arr.length;i++){const x=X(t[i]),y=Y(arr[i]);if(!s){c.moveTo(x,y);s=true;}else c.lineTo(x,y);}c.stroke();}
  if(o.showP&&pr.length)line(pr,COL.prog); if(o.showS&&su.length)line(su,COL.succ);
  if(o.playhead!=null){const x=X(o.playhead);c.strokeStyle='#e7eefc';c.lineWidth=1.5;c.beginPath();c.moveTo(x,T);c.lineTo(x,H-B);c.stroke();}
}

// ---------- command builder ----------
let SRC_RACK='left',SRC_POS=4,DST_RACK='right',DST_POS=3; const SP=[1,3,4,6],DP=[1,3,6];
function mkseg(id,vals,cur,cb){const e=$('#'+id);e.innerHTML='';for(const v of vals){const b=document.createElement('button');b.textContent=(''+v).toUpperCase();if(v===cur)b.classList.add('on');b.onclick=()=>cb(v);e.appendChild(b);}}
function buildSegs(){mkseg('srcRack',['left','right'],SRC_RACK,v=>{SRC_RACK=v;buildSegs();refreshCmd();});mkseg('srcPos',SP,SRC_POS,v=>{SRC_POS=v;buildSegs();refreshCmd();});mkseg('dstRack',['left','right','bin'],DST_RACK,v=>{DST_RACK=v;buildSegs();refreshCmd();});
  const dp=$('#dstPos');dp.innerHTML='';for(const p of DP){const b=document.createElement('button');b.textContent=p;if(DST_RACK==='bin'){b.disabled=true;}else{if(p===DST_POS)b.classList.add('on');b.onclick=()=>{DST_POS=p;buildSegs();refreshCmd();};}dp.appendChild(b);}}
function refreshCmd(){$('#task').value=DST_RACK==='bin'?`Move the vial from position ${SRC_POS} of the ${SRC_RACK} rack to the bin.`:`Move the vial from position ${SRC_POS} of the ${SRC_RACK} rack to slot ${DST_POS} of the ${DST_RACK} rack.`;$('#dur').value=(DST_RACK==='bin')?38:42;}
buildSegs();refreshCmd();

// ---------- cameras ----------
function setPhase(p){$('#phase').className='phase '+(['execute','home','unreachable'].includes(p)?p:'');$('#phaseTxt').textContent=p;}
let polling=false;
async function poll(){if(polling)return;polling=true;try{const j=await(await fetch('/live')).json();const imgs=j.images||{};
  for(const cc of CAMS){const key=imgs[cc]?cc:(Object.keys(imgs).find(x=>x.includes(cc.replace('cam_','')))||null);if(key&&imgs[key])$('#'+cc).src='data:image/jpeg;base64,'+imgs[key];}
  setPhase(j.reachable?(j.phase||'idle'):'unreachable');}catch(e){}finally{polling=false;}}
setInterval(poll,120);poll();

// ---------- live series ----------
async function pollSeries(){try{const s=await(await fetch('/live_series')).json();const now=s.now||0,win=120;
  drawChart($('#liveChart'),{t:s.t,progress:s.progress,success:s.success,markers:s.markers},{tmin:Math.max(0,now-win),tmax:now+2,showP:$('#tP').checked,showS:$('#tS').checked,showC:$('#tC').checked,showR:$('#tR').checked});
  const cur=s.cur;$('#curP').textContent=cur?pct(cur.progress_peak):'–';$('#curS').textContent=cur?pct(cur.success_peak):'–';$('#rbmP').innerHTML=cur&&cur.rbm_prompt?('judging: <span style="color:#cfe0ff">"'+cur.rbm_prompt+'"</span>'):'';}catch(e){}}
setInterval(pollSeries,900);pollSeries();
['tP','tS','tC','tR'].forEach(id=>$('#'+id).addEventListener('change',pollSeries));
async function refreshStats(){try{const s=await(await fetch('/stats')).json();const f=x=>x.fail_pct==null?'–':Math.round(x.fail_pct)+'%';
  $('#sfail').textContent=f(s.session)+(s.session.n?` (${s.session.fail}/${s.session.n})`:'');$('#afail').textContent=f(s.alltime)+(s.alltime.n?` (${s.alltime.fail}/${s.alltime.n})`:'');
  $('#recent').innerHTML=s.recent.slice(0,10).map(r=>`<span style="color:${r.verdict=='1'?'var(--green)':'var(--red)'}">${r.verdict=='1'?'✓':'✗'}</span>`).join(' ');}catch(e){}}
setInterval(refreshStats,4000);refreshStats();
(async()=>{try{const h=await(await fetch('/health')).json();$('#thor').textContent='thor '+(h.thor||'');}catch(e){}})();

// ---------- actions ----------
async function runCmd(){if(busy)return;busy=true;$('#go').disabled=$('#vs').disabled=true;$('#note').textContent='running… (watch the graph)';
  try{await fetch('/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task:$('#task').value,duration:parseFloat($('#dur').value),home_dur:parseFloat($('#home').value)})});$('#note').textContent='done.';}catch(e){$('#note').textContent='failed: '+e;}
  busy=false;$('#go').disabled=$('#vs').disabled=false;refreshStats();}
async function vialSort(){if(busy)return;busy=true;$('#go').disabled=$('#vs').disabled=true;$('#note').textContent='VIAL SORT running…';
  try{await fetch('/vialsort',{method:'POST'});$('#note').textContent='demo done.';}catch(e){$('#note').textContent='failed: '+e;}
  busy=false;$('#go').disabled=$('#vs').disabled=false;refreshStats();}
async function goHome(){if(busy)return;busy=true;$('#homeBtn').disabled=true;try{await fetch('/home',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({duration:parseFloat($('#home').value)})});}catch(e){}busy=false;$('#homeBtn').disabled=false;}
async function openGrip(){$('#note').textContent='opening gripper…';try{await fetch('/release',{method:'POST'});$('#note').textContent='gripper opened.';}catch(e){$('#note').textContent='release failed';}}
async function stopArm(){try{await fetch('/stop',{method:'POST'});}catch(e){}busy=false;$('#go').disabled=$('#vs').disabled=$('#homeBtn').disabled=false;}

// ---------- replay ----------
let RS=null;
async function loadRuns(){try{const j=await(await fetch('/runs')).json();$('#runlist').innerHTML=j.runs.map(r=>`<div class=r data-id="${r.id}" onclick="openRun('${r.id}')"><span>${(r.task||'').slice(0,38)}</span><span class=v style="color:${r.verdict==1?'var(--green)':'var(--red)'}">${r.verdict==null?'—':(r.verdict?'✓':'✗')}</span><br><span style="color:var(--mut);font-size:11px">${r.id}</span></div>`).join('')||'<span style="color:var(--mut)">no recorded runs yet</span>';}catch(e){}}
async function openRun(id){document.querySelectorAll('.runlist .r').forEach(e=>e.classList.toggle('on',e.dataset.id===id));try{RS=await(await fetch('/runs/'+id)).json();}catch(e){return;}
  const v=$('#vid');v.src='/runs/'+id+'/video';v.currentTime=0;$('#rlabel').innerHTML=(RS.task||'')+'  ·  '+(RS.duration||0)+'s  ·  <span style="color:var(--mut)">judging: "'+(RS.rbm_prompt||'')+'"</span>';
  $('#note2').textContent='π0.5 end='+(RS.ctrl_end??'–')+'s · robometer end='+(RS.rbm_end??'–')+'s · peak success='+pct(RS.peak_success)+' (Δ = how early/late Robometer calls it done)';drawReplay(0);}
function replayMarkers(){const m=[];if(RS.ctrl_end!=null)m.push({t:RS.ctrl_end,kind:'ctrl'});if(RS.rbm_end!=null)m.push({t:RS.rbm_end,kind:'rbm'});return m;}
function drawReplay(ph){if(!RS)return;drawChart($('#replayChart'),{t:RS.t,progress:RS.progress,success:RS.success,markers:replayMarkers()},{tmin:0,tmax:RS.duration||(RS.t.length?RS.t[RS.t.length-1]:1),showP:$('#rP').checked,showS:$('#rS').checked,showC:$('#rC').checked,showR:$('#rR').checked,playhead:ph});}
$('#vid').addEventListener('timeupdate',()=>drawReplay($('#vid').currentTime));
['rP','rS','rC','rR'].forEach(id=>$('#'+id).addEventListener('change',()=>drawReplay($('#vid').currentTime||0)));
$('#replayChart').addEventListener('click',e=>{if(!RS)return;const r=e.target.getBoundingClientRect(),L=46,R=16,W=r.width,dur=RS.duration||1;$('#vid').currentTime=Math.max(0,Math.min(dur,(e.clientX-r.left-L)/(W-L-R)*dur));});
window.addEventListener('resize',()=>{pollSeries();if(RS)drawReplay($('#vid').currentTime||0);});
</script></body></html>"""


def main() -> None:
    global SCORER, THRESHOLD, THOR, P_COMPLETE, S_COMPLETE, TRAIL_BIN, TRAIL_RACK
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--server", default=THOR, help="Thor VLA server base URL")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--p-complete", type=float, default=P_COMPLETE)
    ap.add_argument("--s-complete", type=float, default=S_COMPLETE)
    ap.add_argument("--trail-bin", type=float, default=TRAIL_BIN,
                    help="seconds to keep observing past 'execute' on a BIN task (captures the hard-coded gripper-open drop)")
    ap.add_argument("--trail-rack", type=float, default=TRAIL_RACK)
    ap.add_argument("--model-path", default="robometer/Robometer-4B")
    args = ap.parse_args()
    THRESHOLD = args.threshold
    THOR = args.server.rstrip("/")
    P_COMPLETE, S_COMPLETE = args.p_complete, args.s_complete
    TRAIL_BIN, TRAIL_RACK = args.trail_bin, args.trail_rack
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_3FEED_DIR.mkdir(parents=True, exist_ok=True)
    print(f"loading Robometer once (model={args.model_path}) ...")
    SCORER = RobometerScorer(args.model_path)
    threading.Thread(target=_cam_loop, daemon=True).start()
    threading.Thread(target=_observer_loop, daemon=True).start()
    threading.Thread(target=_scorer_loop, daemon=True).start()
    print(f"ready: observer dashboard http://{args.host}:{args.port}  ·  Thor {THOR}  ·  "
          f"complete>=P{P_COMPLETE}/S{S_COMPLETE}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
