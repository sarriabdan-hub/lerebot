#!/usr/bin/env python3
"""
Vial-sort eval logger — walk through a fixed test matrix, score each trial, and
tally per-checkpoint so you can compare checkpoints OBJECTIVELY (not by vibes/loss).

For each trial it tells you how to set up the scene (where to put the RED vial) and
the exact PROMPT. If --server is given it ALSO sends the prompt to the VLA server for
you (POST /execute); otherwise type the prompt into the UI yourself. Then it asks the
OUTCOME and writes a row to a CSV. At the end it prints a score table.

Run on the WS:
    # auto-send the prompt to the robot AND log:
    .venv/bin/python ee/eval_log.py --checkpoint v4_8000 --server http://192.168.123.198:8000
    # log only (you drive the UI yourself):
    .venv/bin/python ee/eval_log.py --checkpoint v4_8000

Outcomes (single key):
    p = PASS            grabbed from source, placed at the named slot
    g = MISS GRASP      went to the right place but grabbed air / missed the pickup
    s = WRONG SLOT      correct rack, wrong position number
    r = WRONG RACK      went to the wrong rack entirely (language-grounding fail)
    c = COLLISION       hit the rack / itself / knocked things over
    d = DROPPED         picked it up then dropped it mid-way
    n = NO MOVE         didn't really move / just oscillated
    o = OTHER           (free text note)
    x = SKIP / redo this trial
Results append to ee/eval_results.csv  (one row per trial, checkpoint tagged).
"""

import argparse
import csv
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

RESULTS = Path(__file__).parent / "eval_results.csv"
DURATION = 41.0  # seconds per execute, matches the UI default

# (destination prompt, where the RED vial STARTS, source rack) — vary the source per trial.
# 3 destinations x 3 source slots = 9 core trials. Edit freely.
TRIALS = [
    # right p6  (vial starts on the LEFT rack)
    ("Place the red vial in position 6 of the right rack.", "LEFT slot 1",  "right p6"),
    ("Place the red vial in position 6 of the right rack.", "LEFT slot 3",  "right p6"),
    ("Place the red vial in position 6 of the right rack.", "LEFT slot 6",  "right p6"),
    # left p1   (vial starts on the RIGHT rack)
    ("Place the red vial in position 1 of the left rack.",  "RIGHT slot 1", "left p1"),
    ("Place the red vial in position 1 of the left rack.",  "RIGHT slot 3", "left p1"),
    ("Place the red vial in position 1 of the left rack.",  "RIGHT slot 6", "left p1"),
    # left p6   (vial starts on the RIGHT rack)
    ("Place the red vial in position 6 of the left rack.",  "RIGHT slot 1", "left p6"),
    ("Place the red vial in position 6 of the left rack.",  "RIGHT slot 3", "left p6"),
    ("Place the red vial in position 6 of the left rack.",  "RIGHT slot 6", "left p6"),
]

OUTCOMES = {
    "p": "PASS", "g": "miss_grasp", "s": "wrong_slot", "r": "wrong_rack",
    "c": "collision", "d": "dropped", "n": "no_move", "o": "other",
}


def send_execute(server: str, task: str):
    body = json.dumps({"task": task, "duration": DURATION}).encode()
    req = urllib.request.Request(f"{server}/execute", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=DURATION + 60) as r:
        return json.loads(r.read())


def home(server: str):
    body = json.dumps({"duration": 4.0}).encode()
    req = urllib.request.Request(f"{server}/home", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True, help="label for this run, e.g. v4_8000")
    ap.add_argument("--server", default=None, help="if set, auto-send prompts (POST /execute)")
    ap.add_argument("--reps", type=int, default=1, help="repeat the whole matrix N times")
    args = ap.parse_args()

    rows = []
    new_file = not RESULTS.exists()
    f = open(RESULTS, "a", newline="")
    w = csv.writer(f)
    if new_file:
        w.writerow(["timestamp", "checkpoint", "destination", "source", "prompt", "outcome", "note"])

    trials = TRIALS * args.reps
    print(f"\n=== EVAL {args.checkpoint} — {len(trials)} trials ===")
    print("Keys: p=pass g=miss-grasp s=wrong-slot r=wrong-rack c=collision d=dropped n=no-move o=other x=redo\n")

    i = 0
    while i < len(trials):
        prompt, source, dest = trials[i]
        print("-" * 70)
        print(f"TRIAL {i+1}/{len(trials)}   destination = {dest}")
        print(f"  1) Put the RED vial at: {source}   (blue distractor: anywhere)")
        print(f"  2) PROMPT: {prompt}")
        if args.server:
            input("  Press ENTER to HOME + EXECUTE (or Ctrl-C to stop)... ")
            try:
                print("  homing..."); home(args.server)
                print("  executing..."); res = send_execute(args.server, prompt)
                print(f"  server: {res}")
            except Exception as e:
                print(f"  !! server error: {e} — log outcome manually anyway")
        else:
            input("  Press Home in the UI, type the prompt, Execute. ENTER when the arm is done... ")

        key = input("  outcome [p/g/s/r/c/d/n/o/x]: ").strip().lower()
        if key == "x":
            print("  (redo this trial)"); continue
        outcome = OUTCOMES.get(key, "other")
        note = input("  note (optional): ").strip() if key == "o" else ""
        ts = dt.datetime.now().isoformat(timespec="seconds")
        w.writerow([ts, args.checkpoint, dest, source, prompt, outcome, note]); f.flush()
        rows.append((dest, outcome))
        i += 1

    f.close()

    # summary
    print("\n" + "=" * 70)
    print(f"SUMMARY — {args.checkpoint}")
    dests = {}
    for dest, outcome in rows:
        d = dests.setdefault(dest, {"pass": 0, "n": 0})
        d["n"] += 1
        if outcome == "PASS":
            d["pass"] += 1
    total_pass = sum(d["pass"] for d in dests.values())
    total_n = sum(d["n"] for d in dests.values())
    for dest, d in sorted(dests.items()):
        print(f"  {dest:10s}: {d['pass']}/{d['n']} passed")
    print(f"  {'TOTAL':10s}: {total_pass}/{total_n}  ({100*total_pass/max(total_n,1):.0f}%)")
    print(f"\n  rows appended to {RESULTS}")
    print("  compare checkpoints:  column -s, -t ee/eval_results.csv | less -S")


if __name__ == "__main__":
    main()
