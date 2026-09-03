#!/usr/bin/env python3
"""
Home the arm — smoothly move it to the rest pose via the warm VLA server.

    .venv/bin/python ee/home.py                 # go to the default home pose
    .venv/bin/python ee/home.py --duration 6    # slower, gentler move
    # override one or more joints (values: body -100..100, gripper 0..100):
    .venv/bin/python ee/home.py --pose "shoulder_lift.pos=-20 gripper.pos=80"

No robot init cost — the server is already warm. Safe to run anytime the arm is in
a weird spot; the move interpolates from wherever it currently is.
"""

import argparse
import json
import urllib.request


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://192.168.123.198:8000")
    ap.add_argument("--duration", type=float, default=4.0)
    ap.add_argument("--pose", default=None,
                    help='partial override, e.g. "shoulder_lift.pos=-20 gripper.pos=80"')
    args = ap.parse_args()

    payload = {"duration": args.duration}
    if args.pose:
        payload["pose"] = {k: float(v) for k, v in
                           (kv.split("=") for kv in args.pose.split())}

    req = urllib.request.Request(f"{args.server}/home", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        print(json.loads(r.read()))


if __name__ == "__main__":
    main()
