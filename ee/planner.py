#!/usr/bin/env python3
"""
VLM planner for vial-sort — FREE LOCAL model via Ollama (no API key, no billing).

Default model: Qwen2.5-VL (qwen2.5vl:7b). Bump to qwen2.5vl:32b for sharper scene
reading (counting the 1x6 slots + colors) — fits easily on a Blackwell 6000.

Runs anywhere Ollama is reachable:
  - workstation (Blackwell 6000):  OLLAMA_URL=http://localhost:11434   (default, recommended)
  - Thor:                          OLLAMA_URL=http://192.168.123.198:11434

Looks at the side-camera image + a high-level goal and emits an ordered plan of ATOMIC
commands in the VLA's trained grammar. All conditional logic ("if the color is wrong,
throw it in the bin") is resolved HERE; the VLA just executes flat commands.

Uses only the Python stdlib (urllib) + Ollama's structured-output `format` (JSON schema),
so the model is forced to return valid JSON — no extra pip installs.
"""

import base64
import json
import os
import urllib.request
from dataclasses import dataclass

import cv2
import numpy as np

MODEL = os.environ.get("VLM_MODEL", "gemma3:27b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# The raw top camera is mounted rotated; rotating CCW90 makes it upright for the VLM
# (arm at top, left rack = source, right rack = goal). VLM-only — the policy sees raw frames.
ROTATE_TOP_CCW90 = True


def _rotate_b64_ccw90(b64_jpeg: str) -> str:
    buf = np.frombuffer(base64.b64decode(b64_jpeg), np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    ok, out = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return base64.b64encode(out.tobytes()).decode("ascii")

# The grammar the VLA understands. Keep the load-bearing tokens (rack side + position
# number, or "bin") exact; the VLM may vary surrounding phrasing.
VIEWS = ["cam_top", "cam_side"]   # order sent to the VLM; cam_top first = primary

SYSTEM = """\
You are the planning layer for a vial-sorting robot arm (SO-101). You produce an
execution plan for a separate low-level policy (a VLA) that can only perform single
atomic commands.

You are shown camera images of the SAME scene. The TOP camera (bird's-eye, shown
first) is the PRIMARY view; the side camera is secondary context.

WHAT THE TOP CAMERA SHOWS (bird's-eye, upright):
- The robot arm is at the TOP of the image.
- The two vial racks are below the arm, side by side.
- The LEFT rack is the SOURCE rack (vials start here).
- The RIGHT rack is the GOAL rack (vials are sorted here).
- Each rack is a line of 6 slots numbered 1..6. SLOT NUMBERING: position 1 is the slot
  NEAREST the robot arm (the top/inner end of the rack); numbers increase moving DOWN/AWAY
  from the arm; position 6 is the far end / boundary (the bottom/outer end).
- There is a BIN for rejected vials. Vials have colors (e.g. red, blue, cyan).

ATOMIC COMMANDS the VLA can execute (use EXACTLY this phrasing, fill in N=1..6):
- "place the vial in the right rack position N"
- "place the vial in the left rack position N"
- "throw the vial in the bin"

CRITICAL RULES:
- Read COLORS and which slots are OCCUPIED only from the image. NEVER copy a position
  number from the goal text into your observation — describe what you actually see.
- Destination positions come from the goal or the sorting rule, NOT from the image.
- For a single "place" command you do NOT need the vial's current slot number — the arm
  sees the vial; just emit the destination command with the position the goal specifies.
- Output an ordered list of steps. Each step is ONE atomic command (one pick + one
  place/throw). Never combine two moves into one step.
- Resolve all conditional logic yourself. E.g. "throw wrong-colored vials in the bin"
  means: for each vial whose color is wrong, emit a "throw the vial in the bin" step.
- "complete vial sort" means: read the colors/occupancy from the image, then produce the
  full ordered sequence of atomic placements that sorts every source vial into the goal rack.
- In `rationale`, justify each step from the visible scene (colors/occupancy you see).
- Respond with JSON only."""

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "observation": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["prompt", "rationale"],
            },
        },
    },
    "required": ["observation", "steps"],
}


@dataclass
class Step:
    prompt: str       # exact atomic command fed to the VLA
    rationale: str    # why, grounded in the scene


@dataclass
class Plan:
    observation: str
    steps: list


def make_plan(images: dict, goal: str,
              model: str = MODEL, ollama_url: str = OLLAMA_URL, views: list = VIEWS) -> Plan:
    """images: {cam_top|cam_side|cam_wrist: base64 JPEG} from the server's /observe.
    The TOP camera leads (primary); side is secondary context."""
    imgs = []
    for v in views:
        if v in images:
            b = images[v]
            if v == "cam_top" and ROTATE_TOP_CCW90:
                b = _rotate_b64_ccw90(b)  # upright for the VLM
            imgs.append((v, b))
    if not imgs:
        raise ValueError(f"none of {views} present in /observe images: {list(images)}")
    desc = "; ".join(f"image {i + 1} = {v}" for i, (v, _) in enumerate(imgs))

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": (f"Images provided ({desc}). The top camera is the primary "
                            f"bird's-eye view for reading slot positions.\n\n"
                            f"High-level goal: {goal}\n\nProduce the execution plan."),
                "images": [b64 for _, b64 in imgs],
            },
        ],
        "stream": False,
        "format": PLAN_SCHEMA,          # Ollama structured output -> guaranteed valid JSON
        "options": {"temperature": 0},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{ollama_url}/api/chat", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.loads(r.read())

    obj = json.loads(resp["message"]["content"])
    steps = [Step(prompt=s["prompt"], rationale=s.get("rationale", "")) for s in obj.get("steps", [])]
    return Plan(observation=obj.get("observation", ""), steps=steps)
