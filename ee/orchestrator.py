#!/usr/bin/env python3
"""
Orchestrator: ties the VLM planner to the warm VLA server (runs on the workstation).

Flow (the policy never re-initializes — the server stays warm the whole time):
    1. GET  /observe   from the Thor VLA server  -> side-camera image
    2. VLM planner(image, goal)                  -> ordered atomic plan
    3. for each step: POST /execute {task, duration} to the server

The planner is a FREE LOCAL VLM (Qwen2.5-VL via Ollama) — no API key, no billing.

Usage:
    # Ollama running on the workstation (default):
    python ee/orchestrator.py \
        --server http://192.168.123.198:8000 \
        --goal "put the red vial from position 3 to position 3 in the right rack" \
        --duration 30

    # just see the plan, don't move the robot:
    python ee/orchestrator.py --server http://192.168.123.198:8000 --goal "..." --plan-only

    # Ollama running on Thor instead of the workstation:
    python ee/orchestrator.py ... --ollama-url http://192.168.123.198:11434
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from planner import MODEL, OLLAMA_URL, make_plan  # noqa: E402


def _get(server: str, path: str, timeout: float = 30.0) -> dict:
    with urllib.request.urlopen(f"{server}{path}", timeout=timeout) as r:
        return json.loads(r.read())


def _post(server: str, path: str, payload: dict, timeout: float = 600.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{server}{path}", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--server", default="http://192.168.123.198:8000",
                   help="Thor VLA server URL")
    p.add_argument("--goal", required=True,
                   help='High-level goal, e.g. "complete vial sort" or '
                        '"put the vial in right rack position 6"')
    p.add_argument("--duration", type=float, default=30.0,
                   help="Seconds per atomic step")
    p.add_argument("--model", default=MODEL, help="Planner VLM (Ollama tag, e.g. qwen2.5vl:7b / :32b)")
    p.add_argument("--ollama-url", default=OLLAMA_URL, help="Ollama endpoint")
    p.add_argument("--plan-only", action="store_true",
                   help="Print the plan and exit; don't move the robot")
    p.add_argument("--yes", action="store_true",
                   help="Execute every step without per-step confirmation")
    return p.parse_args()


def main():
    args = parse_args()

    health = _get(args.server, "/health")
    print(f"Server OK — checkpoint={health.get('checkpoint')} device={health.get('device')}\n")

    print("Observing scene...")
    images = _get(args.server, "/observe")["images"]
    if "cam_top" not in images:
        print(f"ERROR: no cam_top image returned by /observe (got {list(images)}).", file=sys.stderr)
        sys.exit(1)

    print(f"Planning with {args.model} (Ollama @ {args.ollama_url}) — top camera primary...")
    plan = make_plan(images, args.goal, model=args.model, ollama_url=args.ollama_url)

    print(f"\nScene: {plan.observation}\n")
    print(f"Plan ({len(plan.steps)} steps):")
    for i, step in enumerate(plan.steps, 1):
        print(f"  {i}. {step.prompt}")
        print(f"       ↳ {step.rationale}")
    print()

    if args.plan_only:
        return

    for i, step in enumerate(plan.steps, 1):
        if not args.yes:
            ans = input(f"[{i}/{len(plan.steps)}] Execute {step.prompt!r}? [Enter=yes / s=skip / q=quit] ").strip().lower()
            if ans == "q":
                break
            if ans == "s":
                continue
        stats = _post(args.server, "/execute", {"task": step.prompt, "duration": args.duration})
        print(f"    {stats}\n")

    print("Plan complete.")


if __name__ == "__main__":
    main()
