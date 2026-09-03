#!/usr/bin/env python3
"""
Persistent π0 VLA inference server for SO-101 vial-sort (runs on Thor).

WHY THIS EXISTS
    Loading the 4B π0 policy + connecting cameras/motors takes ~3 minutes.
    We do that ONCE at startup, then keep the process alive and accept
    prompts over HTTP. Each VLM-planned step is a cheap /execute call —
    no re-initialization per prompt.

ENDPOINTS
    GET  /health           -> {status, checkpoint, device}
    GET  /observe          -> {images: {cam_top|cam_wrist|cam_side: <b64 jpeg>}, live}
                              While a command is running this returns the LATEST
                              buffered frames captured by the control loop (no
                              robot-bus contention); when idle it captures fresh.
    GET  /state            -> {busy, phase, task, elapsed, duration, n_steps,
                              last_stats}  — cheap status poll for live UIs.
    POST /execute  {task, duration}
                           -> resets the action queue, runs the 30 Hz control
                              loop for `duration` seconds executing `task`,
                              returns latency/step stats.
    POST /home     {duration, pose}
                           -> smoothly interpolates the arm from its current
                              pose to the home/rest pose (no jerk). `pose` is an
                              optional partial {motor.pos: value} override.

CONCURRENCY
    The server is now multi-threaded (ThreadingHTTPServer) but ALL robot access
    is serialized through ROBOT_LOCK, so the motors/serial bus are never touched
    by two requests at once. The one thing that runs concurrently is reading the
    LIVE frame buffer: while /execute or /home holds the robot, the control loop
    keeps publishing JPEG frames into LIVE, and /observe + /state serve from that
    buffer without waiting — which is what lets a dashboard show the cameras and
    the VLA's path live, mid-motion.

USAGE (Jetson Thor, from lerobot repo root, inside tmux):
    python ee/vla_server.py \
        --checkpoint /home/robot/dev/lerebot/pretrained_model \
        --host 0.0.0.0 --port 8000

    # then from the workstation: python ee/orchestrator.py --server http://192.168.123.198:8000 ...

This reuses the proven setup/inference path from rollout_pi0_lora.py; the only
change is that the task string is supplied per-request instead of a global.
"""

import argparse
import base64
import json
import math
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent))                       # ee/ (rollout module)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))        # lerobot src

from lerobot.policies.utils import build_inference_frame, make_robot_action
from lerobot.policies.rtc import ActionQueue, LatencyTracker, reanchor_relative_rtc_prefix
from lerobot.policies.rtc.configuration_rtc import RTCConfig
from lerobot.processor import NormalizerProcessorStep, RelativeActionsProcessorStep
from lerobot.utils.robot_utils import precise_sleep
from rollout_pi0_lora import (  # noqa: E402  reuse the validated setup
    DS_FEATURES,
    FPS,
    build_robot_and_pipelines,
    load_policy_and_processors,
)

# Observation feature spec (must match the training dataset) — drives build_inference_frame:
# it assembles observation.state from the ee.* floats and maps the bare camera keys.
OBS_FEATURES = {
    "observation.state": {"dtype": "float32", "shape": [7],
                          "names": ["ee.x", "ee.y", "ee.z", "ee.wx", "ee.wy", "ee.wz", "ee.gripper_pos"]},
    "observation.images.cam_top":   {"dtype": "video", "shape": [480, 640, 3], "names": ["height", "width", "channels"]},
    "observation.images.cam_wrist": {"dtype": "video", "shape": [480, 640, 3], "names": ["height", "width", "channels"]},
    "observation.images.cam_side":  {"dtype": "video", "shape": [480, 640, 3], "names": ["height", "width", "channels"]},
}


# Home pose = the verified resting/start pose the policy was trained from, so each
# run begins IN-DISTRIBUTION. UPDATED 2026-06-29 to the MEAN first-frame joints of the
# current-pose data (vial-sort-v2-static episodes 42-119 = the 78 eps in v4-ee), NOT v1.
# The old v1 home had wrist_roll=-145 / pan=-0.1 — 18deg / 5deg off from where these demos
# actually start, so the arm began OUT-OF-DISTRIBUTION and flailed for ~10s before snapping
# onto the trained trajectory. Body joints in DEGREES (follower use_degrees=True);
# gripper RANGE_0_100 (3.0 = open). Override per-request with {"pose": {...}} on POST /home.
HOME_POSE = {
    "shoulder_pan.pos": -2.8,
    "shoulder_lift.pos": -106.2,
    "elbow_flex.pos": 96.4,
    "wrist_flex.pos": -102.7,
    "wrist_roll.pos": -165.6,
    "gripper.pos": 0.7,
}


# ── Global state (set once in main, read by the HTTP handler) ───────────────────
STATE: dict = {
    "policy": None,
    "preprocessor": None,
    "postprocessor": None,
    "follower": None,
    "joints_to_ee": None,
    "ee_to_follower": None,
    "device": None,
    "checkpoint": None,
}

# ── Concurrency primitives ──────────────────────────────────────────────────────
# Every function that talks to the robot (get_observation / send_action) must hold
# ROBOT_LOCK, so the serial bus is only ever driven by one request at a time even
# though the HTTP server is threaded. LIVE is the lock-free-ish snapshot the UI
# polls; it's guarded by its own tiny lock so reads never block on the robot.
ROBOT_LOCK = threading.Lock()

# ── motor-bus serialization (patch_bus_lock.py) ──────────────────────────────
# ROBOT_LOCK serializes HTTP requests, but producer threads (--async-chunks /
# --rtc), the safety guard and /observe all touch the serial bus from OTHER
# threads -> "[TxRxResult] Port is in use!". Wrapping the two bus-driving
# methods in one RLock serializes every access, whatever thread it comes from.
BUS_LOCK = threading.RLock()


def _serialize_motor_bus(robot):
    """Make robot.get_observation/send_action thread-safe (idempotent)."""
    if getattr(robot, "_bus_serialized", False):
        return robot
    _get_obs, _send_act = robot.get_observation, robot.send_action

    def get_observation(*a, **kw):
        with BUS_LOCK:
            return _get_obs(*a, **kw)

    def send_action(*a, **kw):
        with BUS_LOCK:
            return _send_act(*a, **kw)

    robot.get_observation = get_observation
    robot.send_action = send_action
    robot._bus_serialized = True
    return robot
# ─────────────────────────────────────────────────────────────────────────────

LIVE_LOCK = threading.Lock()
# Emergency stop: set by POST /stop (which touches NO robot bus, so it returns
# instantly even while /execute holds ROBOT_LOCK). The execute/home loops check it
# every iteration and break, releasing the lock and leaving the arm holding pose.
STOP_EVENT = threading.Event()
LIVE: dict = {
    "busy": False,        # a command (execute/home) is currently driving the arm
    "phase": "idle",      # idle | execute | home | error
    "task": None,         # task string for the running execute
    "t_start": 0.0,       # wall-clock start (time.time) of the running command
    "duration": 0.0,      # requested duration of the running command
    "n_steps": 0,         # control-loop steps taken so far
    "last_stats": None,   # stats dict from the most recent finished command
    "frames": {},         # {short_cam_name: b64 jpeg} — latest buffered frames
    "frame_ts": 0.0,      # perf_counter of the last frame publish (throttle)
}

FRAME_INTERVAL_S = 0.1  # publish at most ~10 fps so JPEG encode never starves the 30 Hz loop


def _set_live(**kw) -> None:
    with LIVE_LOCK:
        LIVE.update(kw)


def _encode_obs_frames(obs_raw: dict) -> dict:
    """Encode every HxWx3 array in an observation to {short_cam_name: b64 jpeg}."""
    out = {}
    for key, val in obs_raw.items():
        if isinstance(val, np.ndarray) and val.ndim == 3 and val.shape[-1] == 3:
            bgr = cv2.cvtColor(val, cv2.COLOR_RGB2BGR)
            ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok:
                out[key.split(".")[-1]] = base64.b64encode(buf.tobytes()).decode("ascii")
    return out


def _find_cam_frame(obs_raw: dict, cam: str):
    """Return the full-res RGB array for a camera (matched by name substring), or None."""
    for key, val in obs_raw.items():
        if isinstance(val, np.ndarray) and val.ndim == 3 and val.shape[-1] == 3 and cam in key:
            return val
    return None


def _publish_frames(obs_raw: dict) -> None:
    """Throttled: push the current observation's frames into LIVE for the UI."""
    now = time.perf_counter()
    if now - LIVE["frame_ts"] < FRAME_INTERVAL_S:
        return
    frames = _encode_obs_frames(obs_raw)
    if frames:
        with LIVE_LOCK:
            LIVE["frames"] = frames
            LIVE["frame_ts"] = now


# ── Inference (task supplied per call — the one difference vs rollout) ───────────

@torch.inference_mode()
def infer_step(obs_raw: dict, task: str) -> tuple[dict, float]:
    device = STATE["device"]
    # build_inference_frame extracts ee.* -> observation.state and cam_* -> observation.images.*,
    # ignoring the raw motor .pos floats, then converts to model-ready tensors.
    obs_batch = build_inference_frame(obs_raw, device, OBS_FEATURES, task)
    obs_batch = STATE["preprocessor"](obs_batch)

    t0 = time.perf_counter()
    action_chunk = STATE["policy"].select_action(obs_batch)
    if device.type == "cuda":
        torch.cuda.synchronize()
    lat = time.perf_counter() - t0

    action_ee = STATE["postprocessor"](action_chunk)
    return make_robot_action(action_ee, DS_FEATURES), lat


def _compute_chunk(task: str):
    """Preprocess the latest obs, predict ONE action chunk, postprocess each step into
    EE-action dicts. Called ONLY from the producer thread (the preprocessor is stateful)."""
    device = STATE["device"]
    obs_ee = STATE["_async_obs"]["obs_ee"]
    obs_batch = build_inference_frame(obs_ee, device, OBS_FEATURES, task)
    obs_batch = STATE["preprocessor"](obs_batch)
    t0 = time.perf_counter()
    chunk = STATE["policy"].predict_action_chunk(obs_batch)  # [1, T, A] (model frame)
    if device.type == "cuda":
        torch.cuda.synchronize()
    lat = time.perf_counter() - t0
    chunk = chunk.squeeze(0)  # [T, A]
    actions = [make_robot_action(STATE["postprocessor"](chunk[t : t + 1]), DS_FEATURES)
               for t in range(chunk.shape[0])]
    return actions, lat


@torch.inference_mode()
def run_command_async(task: str, duration: float) -> dict:
    """Async double-buffer: a background thread does ALL inference (preprocess ->
    predict_action_chunk -> postprocess) and keeps a shared buffer of EE-action dicts
    topped up; the main loop only reads obs, runs IK, and streams actions at FPS, so the
    arm never pauses while the next chunk is computed. ONE thread touches the stateful
    preprocessor/policy -> no race. IK (ee_to_follower) still runs per step on fresh obs."""
    policy = STATE["policy"]
    follower = STATE["follower"]
    joints_to_ee = STATE["joints_to_ee"]
    ee_to_follower = STATE["ee_to_follower"]

    policy.reset()
    STOP_EVENT.clear()
    _set_live(busy=True, phase="execute", task=task, t_start=time.time(),
              duration=duration, n_steps=0, last_stats=None)

    STATE["_async_obs"] = {"obs_ee": None}
    buf: deque = deque()
    buf_lock = threading.Lock()
    obs_lock = threading.Lock()
    done = threading.Event()
    infer_lats: list = []
    refill_at = max(int(getattr(policy.config, "n_action_steps", 50)) // 3, 5)

    def producer():
        while not STOP_EVENT.is_set() and not done.is_set():
            with buf_lock:
                need = len(buf) <= refill_at
            with obs_lock:
                have_obs = STATE["_async_obs"]["obs_ee"] is not None
            if not need or not have_obs:
                precise_sleep(0.005)
                continue
            try:
                actions, lat = _compute_chunk(task)
            except Exception as e:  # noqa: BLE001
                print(f"[async producer] inference error: {e!r}")
                done.set()
                return
            with buf_lock:
                buf.extend(actions)
            infer_lats.append(lat)

    # bootstrap: first obs + first chunk synchronously so the buffer is primed
    obs_raw = follower.get_observation()
    with obs_lock:
        STATE["_async_obs"]["obs_ee"] = joints_to_ee(obs_raw)
    try:
        actions, lat = _compute_chunk(task)
    except Exception as e:  # noqa: BLE001
        _set_live(busy=False, phase="idle")
        return {"task": task, "error": repr(e)}
    buf.extend(actions)
    infer_lats.append(lat)

    prod = threading.Thread(target=producer, name="async-chunk-producer", daemon=True)
    prod.start()

    jit_hist = []
    smooth_alpha = float(STATE.get("smooth_alpha", 1.0))
    gripper_alpha = float(STATE.get("gripper_alpha", 1.0))
    prev_smoothed = None
    prev_grip = None
    ik_seed_last = bool(STATE.get("ik_seed_last"))
    prev_cmd = None
    filter_mode = STATE.get("filter", "ema")
    euro_bank = (_make_euro_bank(float(FPS), float(STATE.get("euro_min_cutoff", 1.0)),
                                 float(STATE.get("euro_beta", 0.05)))
                 if filter_mode == "oneeuro" else None)
    # Optional full-res, full-rate side-cam recording for the presentation (no JPEG/b64 loss).
    rec_cam = STATE.get("record_cam", "cam_side")
    rec_video = bool(STATE.get("record_video"))
    vw = None
    vid_path = Path(__file__).parent / "presentation" / f"exec_{rec_cam}_{int(time.time())}.mp4"
    loop_times, n_steps = [], 0
    guard = _make_safety_guard()
    t_start = time.perf_counter()
    try:
        while time.perf_counter() - t_start < duration and not STOP_EVENT.is_set():
            t_loop = time.perf_counter()
            if guard is not None and (reason := guard.check(follower)):
                _safety_trip(follower, reason)
                break
            obs_raw = follower.get_observation()
            obs_ee = joints_to_ee(obs_raw)
            with obs_lock:
                STATE["_async_obs"]["obs_ee"] = obs_ee

            with buf_lock:
                action_dict = buf.popleft() if buf else None
            if action_dict is None:
                if done.is_set():
                    break  # producer died
                precise_sleep(1.0 / FPS)  # producer catching up — hold this tick
                continue

            obs_for_ik = _seed_obs(obs_raw, prev_cmd) if (ik_seed_last and prev_cmd) else obs_raw
            sent = ee_to_follower((action_dict, obs_for_ik))
            if filter_mode == "oneeuro":
                # 1-Euro: smooth when slow (kills rest/approach jitter), responsive when fast
                # (no lag on the reach/place + crisp gripper close). Beats fixed-EMA's tradeoff.
                sent = _euro_apply(euro_bank, sent)
            else:
                if smooth_alpha < 1.0:
                    # Smooth the JOINT command (post-IK): a smooth EE target still yields jittery
                    # joints because IK re-solves each step from noisy measured joints / jumps
                    # between redundant solutions. Damp what actually goes to the motors.
                    sent = _smooth_action(sent, prev_smoothed, smooth_alpha)
                    prev_smoothed = sent
                if gripper_alpha < 1.0:
                    gk = "gripper.pos" if "gripper.pos" in sent else None
                    if gk is not None:
                        g = float(sent[gk])
                        sent[gk] = g if prev_grip is None else gripper_alpha * g + (1.0 - gripper_alpha) * prev_grip
                        prev_grip = sent[gk]
            follower.send_action(sent)
            if ik_seed_last:
                prev_cmd = {k: v for k, v in sent.items() if k.endswith(".pos")}
            jit_hist.append(_jit_sample(sent))
            _publish_frames(obs_raw)
            if rec_video:
                rgb = _find_cam_frame(obs_raw, rec_cam)
                if rgb is not None:
                    if vw is None:
                        vid_path.parent.mkdir(parents=True, exist_ok=True)
                        h, w = rgb.shape[:2]
                        vw = cv2.VideoWriter(str(vid_path), cv2.VideoWriter_fourcc(*"mp4v"),
                                             float(FPS), (w, h))
                    vw.write(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
            if STATE.get("trace_motors"):
                _trace_row(_motor_trace, time.perf_counter() - t_start, obs_raw, sent, action_dict)
            loop_times.append(time.perf_counter() - t_loop)
            n_steps += 1
            _set_live(n_steps=n_steps)
            precise_sleep(max(1.0 / FPS - (time.perf_counter() - t_loop), 0.0))

        if not n_steps:
            stats = {"task": task, "n_steps": 0, "mode": "async"}
        else:
            stats = {
                "task": task, "n_steps": n_steps, "mode": "async",
                "filter": filter_mode,
                "smooth_alpha": smooth_alpha, "gripper_alpha": gripper_alpha,
                "euro_min_cutoff": STATE.get("euro_min_cutoff", 1.0) if filter_mode == "oneeuro" else None,
                "euro_beta": STATE.get("euro_beta", 0.05) if filter_mode == "oneeuro" else None,
                "jitter_deg": _stats_jitter(jit_hist),
                "duration_s": round(time.perf_counter() - t_start, 2),
                "infer_lat_ms_mean": round(float(np.mean(infer_lats)) * 1000, 1) if infer_lats else None,
                "control_hz_mean": round(float(1.0 / np.mean(loop_times)), 1) if loop_times else None,
            }
        return stats
    finally:
        done.set()
        prod.join(timeout=2.0)
        if vw is not None:
            vw.release()
            print(f"[record] side-cam video -> {vid_path}")
        if STATE.get("trace_motors") and _motor_trace:
            _write_trace(_motor_trace)
        _set_live(busy=False, phase="idle", task=None, last_stats=locals().get("stats"))


def _normalize_prev_len(prev_actions, target_steps):
    """Pad/truncate the RTC prefix to execution_horizon (mirror of rollout/inference/rtc.py)."""
    steps, action_dim = prev_actions.shape
    if steps == target_steps:
        return prev_actions
    if steps > target_steps:
        return prev_actions[:target_steps]
    padded = torch.zeros((target_steps, action_dim), dtype=prev_actions.dtype, device=prev_actions.device)
    padded[:steps] = prev_actions
    return padded


@torch.inference_mode()
def run_command_rtc(task: str, duration: float) -> dict:
    """TRUE Real-Time Chunking (native lerobot RTC).

    Unlike the naive async double-buffer (which *appends* a fresh chunk after the
    leftover tail — the join is a discontinuity = the jitter), RTC feeds the
    unexecuted tail back into predict_action_chunk as `prev_chunk_left_over` so the
    flow model INPAINTS a prefix that continues the tail smoothly (prefix attention),
    then REPLACES the queue accounting for inference delay. No pauses (async), no
    seam jumps (inpainting). For pi05's relative actions the tail is re-anchored to
    the current state via lerobot's reanchor_relative_rtc_prefix — the exact frame
    correctness the IK-seed hack got wrong.
    """
    policy = STATE["policy"]
    follower = STATE["follower"]
    joints_to_ee = STATE["joints_to_ee"]
    ee_to_follower = STATE["ee_to_follower"]
    device = STATE["device"]
    pre = STATE["preprocessor"]
    post = STATE["postprocessor"]

    policy.reset(); pre.reset(); post.reset()
    STOP_EVENT.clear()
    _set_live(busy=True, phase="execute", task=task, t_start=time.time(),
              duration=duration, n_steps=0, last_stats=None)

    EH = int(STATE.get("rtc_execution_horizon", 16))
    threshold = int(STATE.get("rtc_queue_threshold", 25))
    rtc_cfg = RTCConfig(enabled=True, execution_horizon=EH)
    queue = ActionQueue(rtc_cfg)
    latency_tracker = LatencyTracker()

    # CRITICAL: turn RTC on INSIDE the model. _rtc_enabled() checks config.rtc_config;
    # without this the model ignores prev_chunk_left_over entirely (no inpainting → just
    # naive async chunking). init_rtc_processor() builds the RTCProcessor and wires it in.
    policy.config.rtc_config = rtc_cfg
    policy.init_rtc_processor()

    relative_step = next((s for s in pre.steps
                          if isinstance(s, RelativeActionsProcessorStep) and s.enabled), None)
    normalizer_step = next((s for s in pre.steps if isinstance(s, NormalizerProcessorStep)), None)
    if relative_step is not None and relative_step.action_names is None:
        names = getattr(policy.config, "action_feature_names", None)
        relative_step.action_names = list(names) if names else \
            [k for k in DS_FEATURES["action"]["names"]]

    obs_holder = {"obs_ee": None}
    obs_lock = threading.Lock()
    done = threading.Event()
    infer_lats: list = []
    last_real_delay = [0]   # ACTUAL steps consumed during the previous inference (feedback estimate)

    def producer():
        while not STOP_EVENT.is_set() and not done.is_set():
            if queue.qsize() > threshold:
                precise_sleep(0.005); continue
            with obs_lock:
                obs_ee = obs_holder["obs_ee"]
            if obs_ee is None:
                precise_sleep(0.005); continue
            try:
                idx_before = queue.get_action_index()
                prev_actions = queue.get_left_over()
                # inference_delay = how many prefix steps will be consumed while we infer.
                # DON'T derive it from FPS: the loop is bus-limited (~17 Hz, not 30), so
                # latency*FPS over-discards future actions -> skips/starves. Use the ACTUAL
                # count consumed last cycle as the estimate (self-correcting feedback).
                est_delay = last_real_delay[0]

                obs_batch = build_inference_frame(obs_ee, device, OBS_FEATURES, task)
                preprocessed = pre(obs_batch)

                if prev_actions is not None and relative_step is not None:
                    raw_state = relative_step.get_cached_state()
                    if raw_state is not None:
                        prev_abs = queue.get_processed_left_over()
                        if prev_abs is not None and prev_abs.numel() > 0:
                            prev_actions = reanchor_relative_rtc_prefix(
                                prev_actions_absolute=prev_abs, current_state=raw_state,
                                relative_step=relative_step, normalizer_step=normalizer_step,
                                policy_device=device)
                if prev_actions is not None:
                    prev_actions = _normalize_prev_len(prev_actions, EH)

                t0 = time.perf_counter()
                actions = policy.predict_action_chunk(
                    preprocessed, inference_delay=est_delay, prev_chunk_left_over=prev_actions)
                if device.type == "cuda":
                    torch.cuda.synchronize()
                new_lat = time.perf_counter() - t0
                original = actions.squeeze(0).clone()
                processed = post(actions).squeeze(0)
                # GROUND-TRUTH delay: how many actions the consumer actually popped from the
                # OLD queue while this inference ran. FPS-independent; discards exactly the
                # executed prefix, no more (fixes both the skip-miss and the starvation-pause).
                real_delay = max(0, queue.get_action_index() - idx_before)
                last_real_delay[0] = real_delay
                latency_tracker.add(new_lat)
                infer_lats.append(new_lat)
                queue.merge(original, processed, real_delay, idx_before)
            except Exception as e:  # noqa: BLE001
                print(f"[rtc producer] inference error: {e!r}")
                import traceback; traceback.print_exc()
                done.set(); return

    # bootstrap: prime the queue with one obs + one chunk (no prefix)
    obs_raw = follower.get_observation()
    obs_holder["obs_ee"] = joints_to_ee(obs_raw)
    prod = threading.Thread(target=producer, name="rtc-producer", daemon=True)
    prod.start()

    jit_hist = []
    filter_mode = STATE.get("filter", "ema")
    euro_bank = (_make_euro_bank(float(FPS), float(STATE.get("euro_min_cutoff", 1.0)),
                                 float(STATE.get("euro_beta", 0.05)))
                 if filter_mode == "oneeuro" else None)
    loop_times, n_steps = [], 0
    guard = _make_safety_guard()
    t_start = time.perf_counter()
    try:
        while time.perf_counter() - t_start < duration and not STOP_EVENT.is_set():
            t_loop = time.perf_counter()
            if guard is not None and (reason := guard.check(follower)):
                _safety_trip(follower, reason)
                break
            obs_raw = follower.get_observation()
            with obs_lock:
                obs_holder["obs_ee"] = joints_to_ee(obs_raw)

            act = queue.get()
            if act is None:
                if done.is_set():
                    break
                precise_sleep(1.0 / FPS); continue

            action_dict = make_robot_action(act.unsqueeze(0), DS_FEATURES)
            sent = ee_to_follower((action_dict, obs_raw))   # IK on MEASURED obs (correct frame)
            if filter_mode == "oneeuro":
                sent = _euro_apply(euro_bank, sent)         # optional light touch; RTC does the heavy lifting
            follower.send_action(sent)
            jit_hist.append(_jit_sample(sent))
            _publish_frames(obs_raw)
            if STATE.get("trace_motors"):
                _trace_row(_motor_trace, time.perf_counter() - t_start, obs_raw, sent, action_dict)
            loop_times.append(time.perf_counter() - t_loop)
            n_steps += 1
            _set_live(n_steps=n_steps)
            precise_sleep(max(1.0 / FPS - (time.perf_counter() - t_loop), 0.0))

        stats = {
            "task": task, "n_steps": n_steps, "mode": "rtc",
            "rtc_execution_horizon": EH, "rtc_queue_threshold": threshold,
            "filter": filter_mode,
            "jitter_deg": _stats_jitter(jit_hist) if n_steps else None,
            "duration_s": round(time.perf_counter() - t_start, 2),
            "infer_lat_ms_mean": round(float(np.mean(infer_lats)) * 1000, 1) if infer_lats else None,
            "control_hz_mean": round(float(1.0 / np.mean(loop_times)), 1) if loop_times else None,
        }
        return stats
    finally:
        done.set()
        prod.join(timeout=2.0)
        if STATE.get("trace_motors") and _motor_trace:
            _write_trace(_motor_trace)
        _set_live(busy=False, phase="idle", task=None, last_stats=locals().get("stats"))


# ── Action smoothing (EMA low-pass on the EE target to damp step-to-step jitter) ──
def _smooth_action(cur: dict, prev: dict | None, alpha: float) -> dict:
    """Exponential moving average on the EE pose dims (x,y,z,wx,wy,wz). Gripper is left
    untouched so grasp/release stays crisp. alpha=1 -> no smoothing; lower -> smoother/laggier.
    smoothed = alpha*new + (1-alpha)*prev."""
    if prev is None or alpha >= 1.0:
        return dict(cur)
    out = dict(cur)
    for k, v in cur.items():
        if not isinstance(v, (int, float)) or k.endswith("gripper_pos") or k.endswith("gripper.pos"):
            continue
        if k in prev:
            out[k] = alpha * float(v) + (1.0 - alpha) * float(prev[k])
    return out


# ── Per-run structured log (one JSON line per execute: config + stats) ──────────
def _log_run(task: str, duration: float, stats: dict) -> None:
    """Append one JSON line to STATE['log_file'] with the full run config + stats, so the
    whole eval history is in one scp-able file. Cheap, always on once --log-file is set."""
    path = STATE.get("log_file")
    if not path:
        return
    import datetime as _dt
    rec = {
        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
        "checkpoint": STATE.get("checkpoint"),
        "task": task,
        "requested_duration_s": duration,
        "config": {
            "n_action_steps": getattr(STATE["policy"].config, "n_action_steps", None),
            "async_chunks": STATE.get("async_chunks"),
            "smooth_alpha": STATE.get("smooth_alpha"),
            "gripper_alpha": STATE.get("gripper_alpha"),
        },
        "stats": stats,
    }
    try:
        with open(path, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception as e:  # noqa: BLE001
        print(f"[log] failed to write run log: {e!r}")


_JIT_JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]


def _stats_jitter(hist: list) -> float | None:
    """Mean over body joints of step-to-step command std (deg/step) — the smoothness metric."""
    if len(hist) < 3:
        return None
    arr = np.asarray(hist, dtype=float)
    return round(float(np.mean(np.std(np.diff(arr, axis=0), axis=0))), 3)


def _jit_sample(sent: dict) -> list:
    return [float(sent.get(f"{j}.pos", 0.0)) for j in _JIT_JOINTS]


def _seed_obs(obs_raw: dict, prev_cmd: dict) -> dict:
    """Return a shallow copy of obs_raw with the ARM joint positions replaced by the previous
    commanded joints, so the IK seeds from the last solution (stops hopping between branches).
    Cameras / gripper are left as measured."""
    o = dict(obs_raw)
    for j in _JIT_JOINTS:
        k = f"{j}.pos"
        if k in o and k in prev_cmd:
            o[k] = prev_cmd[k]
    return o


# ── 1-Euro filter (adaptive: smooth when slow, responsive when fast) ─────────────
class _OneEuro:
    """Single-channel 1-Euro filter. Lower min_cutoff = smoother at rest (more jitter
    removal); higher beta = more responsive to fast motion (less lag on real moves)."""

    def __init__(self, freq: float, min_cutoff: float, beta: float, d_cutoff: float = 1.0):
        self.freq, self.min_cutoff, self.beta, self.d_cutoff = freq, min_cutoff, beta, d_cutoff
        self._x = None  # last smoothed value
        self._dx = None  # last smoothed derivative
        self._xprev = None

    def _alpha(self, cutoff: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        te = 1.0 / self.freq
        return 1.0 / (1.0 + tau / te)

    def __call__(self, x: float) -> float:
        dx = 0.0 if self._xprev is None else (x - self._xprev) * self.freq
        a_d = self._alpha(self.d_cutoff)
        self._dx = dx if self._dx is None else a_d * dx + (1 - a_d) * self._dx
        cutoff = self.min_cutoff + self.beta * abs(self._dx)
        a = self._alpha(cutoff)
        self._x = x if self._x is None else a * x + (1 - a) * self._x
        self._xprev = x
        return self._x


def _make_euro_bank(freq: float, min_cutoff: float, beta: float) -> dict:
    """Lazily-filled dict of per-joint 1-Euro filters (one per '*.pos' channel)."""
    return {"freq": freq, "min_cutoff": min_cutoff, "beta": beta, "f": {}}


def _euro_apply(bank: dict, sent: dict) -> dict:
    out = dict(sent)
    for k, v in sent.items():
        if not (isinstance(v, (int, float)) and k.endswith(".pos")):
            continue
        f = bank["f"].get(k)
        if f is None:
            f = _OneEuro(bank["freq"], bank["min_cutoff"], bank["beta"])
            bank["f"][k] = f
        out[k] = f(float(v))
    return out


# ── Motor trace (diagnostic, read-only) ─────────────────────────────────────────
_motor_trace: list = []


def _trace_row(buf: list, t_rel: float, obs_raw: dict, sent: dict, action_ee: dict) -> None:
    """Append one row: time + observed joint positions + commanded joint positions + EE action."""
    row = {"t": round(t_rel, 4)}
    for k, v in obs_raw.items():
        if k.endswith(".pos"):
            row[f"obs.{k}"] = round(float(v), 3)
    for k, v in (sent or {}).items():
        if k.endswith(".pos"):
            row[f"cmd.{k}"] = round(float(v), 3)
    for k, v in (action_ee or {}).items():
        if isinstance(v, (int, float)):
            row[f"act.{k}"] = round(float(v), 4)
    buf.append(row)


def _write_trace(buf: list) -> None:
    import csv as _csv
    path = "/tmp/motor_trace.csv"
    keys = list(buf[0].keys())
    with open(path, "w", newline="") as fh:
        wr = _csv.DictWriter(fh, fieldnames=keys)
        wr.writeheader()
        wr.writerows(buf)
    print(f"[trace] wrote {len(buf)} rows -> {path}")
    buf.clear()


class _SafetyGuard:
    """Motor overload watchdog — the thing that would have saved the shoulder_lift servo.

    Called from the control loop (the ONE thread that owns the serial bus, so no
    contention). Every `interval_steps` it sync-reads Present_Temperature and
    Present_Current from all motors. Trips when:
      - any motor temp >= temp_c (approaching the sts3215 ~65C protection point), or
      - any motor draws >= current_ma for `strikes` CONSECUTIVE checks (a stall —
        one spike is normal acceleration; sustained max current means the arm is
        pushing against an obstacle and cooking a winding).
    On trip the caller stops the run and torque-disables the bus (arm goes limp —
    a gentle sag beats a burned servo).
    """

    CURRENT_LSB_MA = 6.5  # sts3215 Present_Current unit

    def __init__(self, temp_c: float, current_ma: float, strikes: int, interval_steps: int,
                 telemetry_path: str | None = None):
        self.temp_c = temp_c
        self.current_ma = current_ma
        self.strikes = max(1, strikes)
        self.interval = max(1, interval_steps)
        self.telemetry_path = telemetry_path
        self._overcurrent: dict = {}
        self._n = 0

    def _emit_telemetry(self, temps: dict, currents_ma: dict) -> None:
        """One JSON line per check — Telegraf tails this into InfluxDB/Grafana."""
        if not self.telemetry_path:
            return
        try:
            line = {"ts": round(time.time(), 3),
                    **{f"temp.{m}": float(t) for m, t in temps.items()},
                    **{f"ma.{m}": round(v, 1) for m, v in currents_ma.items()}}
            with open(self.telemetry_path, "a") as fh:
                fh.write(json.dumps(line) + "\n")
        except Exception:
            pass  # telemetry must never affect the control loop

    def check(self, follower) -> str | None:
        """Returns a trip-reason string, or None if all clear. Never raises."""
        self._n += 1
        if self._n % self.interval:
            return None
        try:
            temps = follower.bus.sync_read("Present_Temperature", normalize=False, num_retry=1)
            currents = follower.bus.sync_read("Present_Current", normalize=False, num_retry=1)
        except Exception:
            return None  # a dropped safety read must never kill a healthy run
        currents_ma = {}
        for m, c in currents.items():
            raw = int(c)
            if raw > 32767:   # Feetech sign convention: bit15 = direction, magnitude below
                raw -= 32768
            currents_ma[m] = abs(raw) * self.CURRENT_LSB_MA
        self._emit_telemetry(temps, currents_ma)
        for m, t in temps.items():
            if float(t) >= self.temp_c and float(t) > 0:  # 0 = bogus read, ignore
                return f"OVERHEAT {m}={t}C >= {self.temp_c}C"
        for m, ma in currents_ma.items():
            if ma >= self.current_ma:
                self._overcurrent[m] = self._overcurrent.get(m, 0) + 1
                if self._overcurrent[m] >= self.strikes:
                    return f"STALL {m}={ma:.0f}mA >= {self.current_ma}mA x{self.strikes} checks"
            else:
                self._overcurrent[m] = 0
        return None


def _make_safety_guard() -> "_SafetyGuard | None":
    if not STATE.get("safety", True):
        return None
    return _SafetyGuard(temp_c=float(STATE.get("safety_temp_c", 55.0)),
                        current_ma=float(STATE.get("safety_current_ma", 1400.0)),
                        strikes=int(STATE.get("safety_strikes", 3)),
                        interval_steps=int(STATE.get("safety_interval_steps", 10)),
                        telemetry_path=STATE.get("telemetry_file") or None)


def _safety_trip(follower, reason: str) -> None:
    """Stop everything and de-energize: the burned-servo lesson, in code."""
    print(f"\n*** SAFETY TRIP: {reason} — stopping run + disabling torque ***\n")
    STOP_EVENT.set()
    try:
        follower.bus.disable_torque(num_retry=5)
    except Exception as e:  # still report even if the bus is wedged
        print(f"[safety] torque-disable failed: {e!r} — CUT POWER MANUALLY")
    _set_live(phase="error", last_stats={"safety_trip": reason})


def run_command(task: str, duration: float) -> dict:
    """Run ONE atomic command for `duration` seconds. Fresh action queue each call."""
    if STATE.get("rtc"):
        return run_command_rtc(task, duration)
    if STATE.get("async_chunks"):
        return run_command_async(task, duration)
    policy = STATE["policy"]
    follower = STATE["follower"]
    joints_to_ee = STATE["joints_to_ee"]
    ee_to_follower = STATE["ee_to_follower"]

    policy.reset()  # CRITICAL: drop any chunked actions queued for the previous prompt
    STOP_EVENT.clear()  # fresh run — clear any leftover stop from a previous command

    _set_live(busy=True, phase="execute", task=task, t_start=time.time(),
              duration=duration, n_steps=0, last_stats=None)

    smooth_alpha = float(STATE.get("smooth_alpha", 1.0))
    gripper_alpha = float(STATE.get("gripper_alpha", 1.0))
    prev_smoothed = None
    prev_grip = None
    filter_mode = STATE.get("filter", "ema")
    euro_bank = (_make_euro_bank(float(FPS), float(STATE.get("euro_min_cutoff", 1.0)),
                                 float(STATE.get("euro_beta", 0.05)))
                 if filter_mode == "oneeuro" else None)
    ik_seed_last = bool(STATE.get("ik_seed_last"))
    prev_cmd = None
    rec_cam = STATE.get("record_cam", "cam_side")
    rec_video = bool(STATE.get("record_video"))
    vw = None
    vid_path = Path(__file__).parent / "presentation" / f"exec_{rec_cam}_{int(time.time())}.mp4"

    infer_lats, loop_times, n_steps, jit_hist = [], [], 0, []
    guard = _make_safety_guard()
    t_start = time.perf_counter()
    try:
        while time.perf_counter() - t_start < duration and not STOP_EVENT.is_set():
            t_loop = time.perf_counter()
            if guard is not None and (reason := guard.check(follower)):
                _safety_trip(follower, reason)
                break

            obs_raw = follower.get_observation()
            obs_ee = joints_to_ee(obs_raw)

            action_dict, lat = infer_step(obs_ee, task)
            obs_for_ik = _seed_obs(obs_raw, prev_cmd) if (ik_seed_last and prev_cmd) else obs_raw
            follower_joints = ee_to_follower((action_dict, obs_for_ik))
            if filter_mode == "oneeuro":
                follower_joints = _euro_apply(euro_bank, follower_joints)
            else:
                if smooth_alpha < 1.0:
                    follower_joints = _smooth_action(follower_joints, prev_smoothed, smooth_alpha)
                    prev_smoothed = follower_joints
                if gripper_alpha < 1.0 and "gripper.pos" in follower_joints:
                    g = float(follower_joints["gripper.pos"])
                    follower_joints["gripper.pos"] = g if prev_grip is None else gripper_alpha * g + (1.0 - gripper_alpha) * prev_grip
                    prev_grip = follower_joints["gripper.pos"]
            follower.send_action(follower_joints)
            if ik_seed_last:
                prev_cmd = {k: v for k, v in follower_joints.items() if k.endswith(".pos")}
            jit_hist.append(_jit_sample(follower_joints))

            _publish_frames(obs_raw)  # feed the live dashboard mid-motion
            if rec_video:
                rgb = _find_cam_frame(obs_raw, rec_cam)
                if rgb is not None:
                    if vw is None:
                        vid_path.parent.mkdir(parents=True, exist_ok=True)
                        h, w = rgb.shape[:2]
                        vw = cv2.VideoWriter(str(vid_path), cv2.VideoWriter_fourcc(*"mp4v"),
                                             float(FPS), (w, h))
                    vw.write(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
            if STATE.get("trace_motors"):
                _trace_row(_motor_trace, time.perf_counter() - t_start, obs_raw, follower_joints, action_dict)

            infer_lats.append(lat)
            loop_times.append(time.perf_counter() - t_loop)
            n_steps += 1
            _set_live(n_steps=n_steps)
            precise_sleep(max(1.0 / FPS - (time.perf_counter() - t_loop), 0.0))

        if not infer_lats:
            stats = {"task": task, "n_steps": 0}
        else:
            stats = {
                "task": task,
                "n_steps": n_steps,
                "filter": filter_mode,
                "smooth_alpha": smooth_alpha, "gripper_alpha": gripper_alpha,
                "euro_min_cutoff": STATE.get("euro_min_cutoff", 1.0) if filter_mode == "oneeuro" else None,
                "euro_beta": STATE.get("euro_beta", 0.05) if filter_mode == "oneeuro" else None,
                "jitter_deg": _stats_jitter(jit_hist),
                "duration_s": round(time.perf_counter() - t_start, 2),
                "infer_lat_ms_mean": round(float(np.mean(infer_lats)) * 1000, 1),
                "infer_lat_ms_p95": round(float(np.percentile(infer_lats, 95)) * 1000, 1),
                "control_hz_mean": round(float(1.0 / np.mean(loop_times)), 1),
            }
        return stats
    finally:
        if vw is not None:
            vw.release()
            print(f"[record] side-cam video -> {vid_path}")
        if STATE.get("trace_motors") and _motor_trace:
            _write_trace(_motor_trace)
        _set_live(busy=False, phase="idle", task=None, last_stats=locals().get("stats"))


def go_home(duration: float = 4.0, pose: dict | None = None) -> dict:
    """Smoothly drive the arm from its CURRENT pose to the home pose.

    Interpolates joint-by-joint at FPS so there's no jerk no matter where the arm
    starts. `pose` (a partial {motor.pos: value} dict) overrides HOME_POSE entries.
    """
    follower = STATE["follower"]
    STATE["policy"].reset()  # drop any queued VLA actions so they don't fight the homing

    target = dict(HOME_POSE)
    if pose:
        target.update(pose)

    obs = follower.get_observation()
    cur = {k: float(v) for k, v in obs.items() if k.endswith(".pos")}
    keys = [k for k in target if k in cur]  # only joints the robot actually reports
    if not keys:
        return {"error": "no matching joints", "robot_keys": sorted(cur)}

    _set_live(busy=True, phase="home", task=None, t_start=time.time(),
              duration=duration, n_steps=0, last_stats=None)
    _publish_frames(obs)

    STOP_EVENT.clear()
    n = max(int(duration * FPS), 1)
    try:
        for i in range(1, n + 1):
            if STOP_EVENT.is_set():
                break
            a = i / n
            step = {k: cur[k] + (target[k] - cur[k]) * a for k in keys}
            follower.send_action(step)
            # periodically refresh the live frames so the UI sees the homing move
            if time.perf_counter() - LIVE["frame_ts"] >= FRAME_INTERVAL_S:
                _publish_frames(follower.get_observation())
            _set_live(n_steps=i)
            precise_sleep(1.0 / FPS)
        return {"homed_to": {k: round(target[k], 2) for k in keys}, "steps": n,
                "duration_s": round(duration, 2)}
    finally:
        _set_live(busy=False, phase="idle")


def capture_images() -> dict:
    """Return {short_cam_name: b64 jpeg} for every image-like array in the observation,
    regardless of key naming (the robot keys cameras as bare names like 'cam_top').
    Caller MUST hold ROBOT_LOCK — this drives the serial bus."""
    obs_raw = STATE["follower"].get_observation()
    out = {}
    for key, val in obs_raw.items():
        if isinstance(val, np.ndarray) and val.ndim == 3 and val.shape[-1] == 3:
            bgr = cv2.cvtColor(val, cv2.COLOR_RGB2BGR)
            ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                short = key.split(".")[-1]  # 'cam_top' etc, stripping any prefix
                out[short] = base64.b64encode(buf.tobytes()).decode("ascii")
    return out


def observe_images() -> dict:
    """Frames for the UI, never blocking on a running command.

    While the arm is busy (execute/home holds ROBOT_LOCK) we return the latest
    frames the control loop buffered. When idle we grab a fresh frame — but only
    via a non-blocking lock acquire, so if a command starts in the same instant we
    fall back to the buffer instead of stalling for the whole command.
    """
    with LIVE_LOCK:
        busy, buffered = LIVE["busy"], dict(LIVE["frames"])
    if not busy and ROBOT_LOCK.acquire(timeout=0.5):
        try:
            fresh = capture_images()
        finally:
            ROBOT_LOCK.release()
        _set_live(frames=fresh, frame_ts=time.perf_counter())
        return {"images": fresh, "live": False}
    return {"images": buffered, "live": busy}


def state_snapshot() -> dict:
    with LIVE_LOCK:
        s = {k: LIVE[k] for k in ("busy", "phase", "task", "duration", "n_steps", "last_stats")}
        s["elapsed"] = round(time.time() - LIVE["t_start"], 2) if LIVE["busy"] else 0.0
    return s


# ── Dashboard ────────────────────────────────────────────────────────────────────
# Minimal control panel served at "/". Note: the server is single-threaded, so while
# an /execute or /home is running the page's fetches will block until it finishes —
# that's expected (the buttons show "running…").

DASHBOARD_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>VLA server</title><style>
 body{font-family:system-ui,sans-serif;margin:20px;background:#111;color:#eee}
 h1{font-size:18px} .cams{display:flex;gap:10px;flex-wrap:wrap}
 .cam{text-align:center} .cam img{max-width:320px;border:1px solid #444;border-radius:6px}
 button{padding:8px 14px;margin:4px;border:0;border-radius:6px;background:#2d6cdf;color:#fff;cursor:pointer}
 button.warn{background:#c0392b} input{padding:7px;border-radius:6px;border:1px solid #555;background:#222;color:#eee}
 #status{white-space:pre-wrap;background:#000;padding:10px;border-radius:6px;margin-top:10px;min-height:20px}
 .row{margin:8px 0}
</style></head><body>
<h1>π0 VLA server</h1>
<div id="health">health: …</div>
<div class="row">
  <button onclick="refresh()">Refresh cameras</button>
  <label><input type="checkbox" id="auto"> auto every 2s</label>
</div>
<div class="cams" id="cams"></div>
<div class="row">
  <button class="warn" onclick="home()">Home arm</button>
  home duration <input id="hdur" type="number" value="4" style="width:60px">s
</div>
<div class="row">
  <input id="task" size="48" value="Place the red vial in position 3 of the right rack.">
  dur <input id="dur" type="number" value="30" style="width:60px">s
  <button onclick="execute()">Execute</button>
</div>
<div id="status"></div>
<script>
const $=id=>document.getElementById(id);
function log(x){$('status').textContent=(typeof x==='string'?x:JSON.stringify(x,null,2));}
async function health(){try{const r=await fetch('/health');const j=await r.json();
  $('health').textContent='health: '+JSON.stringify(j);}catch(e){$('health').textContent='health: unreachable';}}
async function refresh(){try{const r=await fetch('/observe');const j=await r.json();
  const c=$('cams');c.innerHTML='';for(const[k,v]of Object.entries(j.images||{})){
    const d=document.createElement('div');d.className='cam';
    d.innerHTML='<div>'+k+'</div><img src="data:image/jpeg;base64,'+v+'">';c.appendChild(d);}
  }catch(e){log('refresh failed (server busy?): '+e);}}
async function home(){log('homing… (arm moving)');try{const r=await fetch('/home',{method:'POST',
  headers:{'Content-Type':'application/json'},body:JSON.stringify({duration:parseFloat($('hdur').value)})});
  log(await r.json());}catch(e){log('home failed: '+e);}}
async function execute(){log('executing… (arm moving, page blocks until done)');try{
  const r=await fetch('/execute',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({task:$('task').value,duration:parseFloat($('dur').value)})});
  log(await r.json());}catch(e){log('execute failed: '+e);}}
setInterval(()=>{if($('auto').checked)refresh();},2000);
health();refresh();
</script></body></html>"""


# ── HTTP handler ────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        # A long /execute often outlives the client (curl -m timeout, closed UI
        # tab). Writing to that dead socket raises BrokenPipeError, and the
        # handler's 500-fallback then raises AGAIN on the same socket -> two
        # scary tracebacks for what is just "nobody was listening". The command
        # itself already completed; swallow it.
        body = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            print(f"[http] client disconnected before the {code} reply "
                  f"(harmless — the command itself finished)")

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # quieter logs
        return

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._send_html(DASHBOARD_HTML)
        elif self.path == "/health":
            self._send(200, {
                "status": "ok",
                "checkpoint": STATE["checkpoint"],
                "device": str(STATE["device"]),
            })
        elif self.path == "/observe":
            try:
                self._send(200, observe_images())
            except Exception as e:  # noqa: BLE001
                self._send(500, {"error": repr(e)})
        elif self.path == "/state":
            self._send(200, state_snapshot())
        else:
            self._send(404, {"error": "unknown path"})

    def do_POST(self):
        if self.path == "/stop":
            # Emergency stop: set the flag and return immediately. Touches no robot
            # bus, so it does NOT wait on ROBOT_LOCK held by a running /execute.
            STOP_EVENT.set()
            print("[stop] EMERGENCY STOP requested")
            self._send(200, {"stopped": True})
            return
        if self.path not in ("/execute", "/home", "/tune"):
            self._send(404, {"error": "unknown path"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
        except Exception as e:  # noqa: BLE001
            self._send(400, {"error": f"bad request: {e!r}"})
            return

        if self.path == "/tune":
            # Live-tune inference knobs WITHOUT restarting (no 3-min reload). Applied on
            # the NEXT execute (each run reads these from STATE at its start).
            for key in ("smooth_alpha", "gripper_alpha", "euro_min_cutoff", "euro_beta"):
                if key in req and req[key] is not None:
                    STATE[key] = float(req[key])
            if req.get("filter") in ("ema", "oneeuro"):
                STATE["filter"] = req["filter"]
            if req.get("ik_seed_last") is not None:
                STATE["ik_seed_last"] = bool(req["ik_seed_last"])
            if req.get("n_action_steps") is not None:
                STATE["policy"].config.n_action_steps = int(req["n_action_steps"])
            cur = {
                "filter": STATE.get("filter", "ema"),
                "smooth_alpha": STATE.get("smooth_alpha", 1.0),
                "gripper_alpha": STATE.get("gripper_alpha", 1.0),
                "euro_min_cutoff": STATE.get("euro_min_cutoff", 1.0),
                "euro_beta": STATE.get("euro_beta", 0.05),
                "ik_seed_last": STATE.get("ik_seed_last", False),
                "n_action_steps": getattr(STATE["policy"].config, "n_action_steps", None),
                "async_chunks": STATE.get("async_chunks"),
            }
            print(f"[tune] {cur}")
            self._send(200, cur)
            return

        if self.path == "/home":
            try:
                duration = float(req.get("duration", 4.0))
                print(f"[home] duration={duration}s pose_override={req.get('pose')}")
                with ROBOT_LOCK:  # serialize all robot access
                    stats = go_home(duration, req.get("pose"))
                print(f"[home] done: {stats}")
                self._send(200, stats)
            except Exception as e:  # noqa: BLE001
                _set_live(busy=False, phase="error")
                self._send(500, {"error": repr(e)})
            return

        try:
            task = req["task"]
            duration = float(req.get("duration", 30.0))
        except Exception as e:  # noqa: BLE001
            self._send(400, {"error": f"bad request: {e!r}"})
            return
        try:
            print(f"[execute] task={task!r} duration={duration}s")
            with ROBOT_LOCK:  # serialize all robot access
                stats = run_command(task, duration)
            print(f"[execute] done: {stats}")
            _log_run(task, duration, stats)
            self._send(200, stats)
        except Exception as e:  # noqa: BLE001
            _set_live(busy=False, phase="error")
            self._send(500, {"error": repr(e)})


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", default="/home/robot/dev/lerebot/pretrained_model",
                   help="π0 checkpoint dir (default = rsync target; the 100-ep fullft run)")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--device", default=None)
    p.add_argument("--n-action-steps", type=int, default=None,
                   help="Override the policy's action horizon (steps executed before re-observing). "
                        "Lower (10-20) = more closed-loop grasp correction. Default None = use checkpoint config (50).")
    p.add_argument("--async-chunks", action="store_true",
                   help="Run inference in a background thread (async double-buffer) so the arm "
                        "never pauses while the next chunk is computed. Smoother motion. "
                        "Pair with a larger --n-action-steps (e.g. 50) so chunks are big enough to hide latency.")
    p.add_argument("--trace-motors", action="store_true",
                   help="Log per-step observed+commanded joint positions to /tmp/motor_trace.csv "
                        "(diagnostic: shows which joint jiggles). Async path only.")
    p.add_argument("--smooth-alpha", type=float, default=1.0,
                   help="EMA smoothing on the JOINT command post-IK to damp step-to-step jitter "
                        "(async path). 1.0=off, 0.5=moderate, 0.3=heavy. Gripper handled separately. Start at 0.4.")
    p.add_argument("--gripper-alpha", type=float, default=1.0,
                   help="Separate EMA on the gripper to stop open/close chatter (the 'puts it back' "
                        "flutter). 1.0=off, 0.5=moderate, 0.3=heavy. Start at 0.5; too low = weak/slow grasp.")
    p.add_argument("--record-video", action="store_true",
                   help="Record the full-res, full-rate camera (default cam_side) of each execute to "
                        "ee/presentation/exec_*.mp4 — clean, no JPEG/overlay loss. For the presentation.")
    p.add_argument("--record-cam", default="cam_side",
                   help="Which camera to record with --record-video (substring match: cam_side/cam_top/cam_wrist).")
    p.add_argument("--filter", default="ema", choices=["ema", "oneeuro"],
                   help="Smoothing filter on the joint command. 'ema'=fixed alpha; "
                        "'oneeuro'=adaptive (smooth when slow, responsive when fast — best for grasp).")
    p.add_argument("--euro-min-cutoff", type=float, default=1.0,
                   help="1-Euro min cutoff Hz. LOWER = smoother at rest (more jitter removal). Start 1.0.")
    p.add_argument("--euro-beta", type=float, default=0.05,
                   help="1-Euro beta. HIGHER = more responsive to fast motion (less lag). Start 0.05.")
    p.add_argument("--ik-seed-last", action="store_true",
                   help="Seed the IK from the previous COMMANDED joints (not measured) so it stops "
                        "hopping between solutions — removes joint jitter at the source.")
    p.add_argument("--ik-prev-solution", action="store_true",
                   help="ROOT-CAUSE jitter fix (layer B): seed the IK from the PREVIOUS SOLUTION "
                        "instead of from noisy measured joints every step, so the solver stops "
                        "hopping between redundant joint solutions for a stable absolute EE pose. "
                        "Safe (absolute target, no filter feedback) — unlike the old --ik-seed-last.")
    p.add_argument("--rtc", action="store_true",
                   help="TRUE Real-Time Chunking (native lerobot): async inference that INPAINTS the "
                        "next chunk's prefix to continue the executing tail (prefix attention) instead "
                        "of splicing a fresh chunk. No pauses AND no seam jitter. Relative actions "
                        "re-anchored correctly. Supersedes --async-chunks; smoothing largely unneeded.")
    p.add_argument("--rtc-execution-horizon", type=int, default=16,
                   help="RTC prefix/guidance horizon (how many leftover steps guide the next chunk). "
                        "Higher = smoother handoff but more constrained; 10-20 typical.")
    p.add_argument("--rtc-queue-threshold", type=int, default=25,
                   help="Re-infer when the action queue drops to this many remaining steps.")
    p.add_argument("--no-safety", action="store_true",
                   help="Disable the motor overload watchdog (temp + stall-current checks "
                        "during execute; trips -> stop + torque off). Leave ON.")
    p.add_argument("--safety-temp-c", type=float, default=55.0,
                   help="Trip if any motor reaches this temperature (sts3215 protection ~65C).")
    p.add_argument("--safety-current-ma", type=float, default=1400.0,
                   help="Stall-current trip level in mA (sustained). ~1A = hard push for sts3215.")
    p.add_argument("--safety-strikes", type=int, default=3,
                   help="Consecutive over-current checks before tripping (filters accel spikes).")
    p.add_argument("--safety-interval-steps", type=int, default=10,
                   help="Control-loop steps between safety reads (~0.5s at 17-30Hz).")
    p.add_argument("--telemetry-file", default="/tmp/motor_telemetry.jsonl",
                   help="JSONL of per-check motor temps (C) + currents (mA) — Telegraf tails "
                        "this into InfluxDB/Grafana (see ee/telegraf_motor.conf). '' disables.")
    p.add_argument("--log-file", default="/tmp/vla_runs.jsonl",
                   help="Append one JSON line per execute (config + stats) here. scp it for analysis. "
                        "Set to '' to disable.")
    return p.parse_args()


def main():
    args = parse_args()
    device = torch.device(args.device or ("cuda" if torch.cuda.is_available() else "cpu"))
    print(f"Device: {device}")

    print("Loading policy (this is the slow part, ~minutes)...")
    policy, preprocessor, postprocessor = load_policy_and_processors(args.checkpoint, device)
    if args.n_action_steps is not None:
        # Shorten the action horizon so the policy re-observes more often -> closed-loop
        # grasp correction (research: 10-20 beats 50 for grasp reliability). The action
        # queue is rebuilt from this in policy.reset() (deque maxlen=n_action_steps).
        policy.config.n_action_steps = args.n_action_steps
        print(f"  n_action_steps overridden -> {args.n_action_steps} (was checkpoint default)")
    print("Connecting robot (cameras warm up here)...")
    follower, joints_to_ee, ee_to_follower = build_robot_and_pipelines(
        dry_run=False, ik_from_prev_solution=args.ik_prev_solution)
    follower = _serialize_motor_bus(follower)  # patch_bus_lock.py

    STATE.update(policy=policy, preprocessor=preprocessor, postprocessor=postprocessor,
                 follower=follower, joints_to_ee=joints_to_ee, ee_to_follower=ee_to_follower,
                 device=device, checkpoint=str(args.checkpoint),
                 async_chunks=args.async_chunks, trace_motors=args.trace_motors,
                 smooth_alpha=args.smooth_alpha, gripper_alpha=args.gripper_alpha,
                 record_video=args.record_video, record_cam=args.record_cam,
                 log_file=(args.log_file or None),
                 filter=args.filter, euro_min_cutoff=args.euro_min_cutoff, euro_beta=args.euro_beta,
                 ik_seed_last=args.ik_seed_last, rtc=args.rtc,
                 rtc_execution_horizon=args.rtc_execution_horizon,
                 rtc_queue_threshold=args.rtc_queue_threshold,
                 safety=not args.no_safety, safety_temp_c=args.safety_temp_c,
                 safety_current_ma=args.safety_current_ma, safety_strikes=args.safety_strikes,
                 safety_interval_steps=args.safety_interval_steps,
                 telemetry_file=(args.telemetry_file or None))
    if args.telemetry_file:
        print(f"  motor telemetry -> {args.telemetry_file} (Telegraf: ee/telegraf_motor.conf)")
    if args.no_safety:
        print("  !!! SAFETY WATCHDOG OFF — motors are unprotected against stall/overheat !!!")
    else:
        print(f"  safety watchdog ON: trip at {args.safety_temp_c}C or "
              f"{args.safety_current_ma}mA x{args.safety_strikes} (checked every {args.safety_interval_steps} steps)")
    if args.rtc:
        print(f"  RTC ON (native lerobot): execution_horizon={args.rtc_execution_horizon} "
              f"queue_threshold={args.rtc_queue_threshold} — inpainted async chunking, no seam jitter")
    if args.filter == "oneeuro":
        print(f"  1-Euro filter ON: min_cutoff={args.euro_min_cutoff} beta={args.euro_beta}")
    if args.ik_seed_last:
        print("  ik-seed-last ON: IK seeds from previous command (anti-hop)")
    if args.log_file:
        print(f"  run log: one JSON line per execute -> {args.log_file}")
    if args.record_video:
        print(f"  record-video ON: full-res {args.record_cam} -> ee/presentation/exec_*.mp4 per execute")
    if args.async_chunks:
        print("  async-chunks ON: inference runs in a background thread (no pauses)")
    if args.smooth_alpha < 1.0:
        print(f"  joint smoothing ON: EMA alpha={args.smooth_alpha} (joint command post-IK)")
    if args.gripper_alpha < 1.0:
        print(f"  gripper smoothing ON: EMA alpha={args.gripper_alpha}")
    if args.trace_motors:
        print("  trace-motors ON: per-step joints -> /tmp/motor_trace.csv")

    # Warm up CUDA kernels so the first real /execute isn't slow.
    print("Warming up...")
    fake = {k: 0.0 for k in ["ee.x", "ee.y", "ee.z", "ee.wx", "ee.wy", "ee.wz", "ee.gripper_pos"]}
    for cam in ("cam_top", "cam_wrist", "cam_side"):
        fake[cam] = np.zeros((480, 640, 3), dtype=np.uint8)
    for _ in range(3):
        infer_step(fake, "warmup")
    policy.reset()

    # Threaded so /observe + /state can serve the live frame buffer WHILE /execute
    # or /home is driving the arm. Robot access itself stays serialized via ROBOT_LOCK.
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    print(f"\nVLA server ready on http://{args.host}:{args.port}  (init done — stays warm)\n"
          f"  GET  /health  /observe  /state   POST /execute {{task, duration}}   POST /home {{duration, pose}}\n"
          "Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        if follower and follower.is_connected:
            follower.disconnect()


if __name__ == "__main__":
    main()
