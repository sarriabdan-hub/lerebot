#!/usr/bin/env python3
"""Fix the motor-bus contention ("[TxRxResult] Port is in use!") in vla_server.py.

ROOT CAUSE (Thor session 2026-07-18): several THREADS drive the Feetech serial
bus concurrently. ROBOT_LOCK only serializes HTTP *requests*, but:
  * with --async-chunks the "async-chunk-producer" thread calls
    follower.get_observation() (L~264/303) while the executor loop calls it too
    (L~840) — same /execute, two threads, one serial port;
  * the RTC producer thread does the same (L~500/519);
  * the safety guard reads Present_Temperature/Current from its own context;
  * /observe -> observe_images() -> capture_images() -> get_observation().
None of those go through ROBOT_LOCK, so two threads hit /dev/ttyACM0 at once.

THE FIX: wrap the follower's get_observation/send_action in a re-entrant lock at
the moment it is created, so EVERY caller on EVERY thread is serialized, with no
need to touch dozens of call sites. RLock => nested calls on one thread are fine.

This script is IDEMPOTENT and surgical: it only inserts the wrapper + one call.
It does NOT overwrite the file, so Thor's own fixes (preflight_realsense,
connect_robot_with_timeout, the flash-attn/sdpa work) are preserved.

Run ON THOR:
    python /home/robot/dev/lerebot/ee/patch_bus_lock.py \
        /home/robot/dev/lerebot/ee/vla_server.py
Then restart vla_server.py.
"""

import re
import shutil
import sys
from pathlib import Path

WRAPPER = '''
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
'''

CALL = "    follower = _serialize_motor_bus(follower)  # patch_bus_lock.py\n"


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "ee/vla_server.py")
    src = path.read_text()

    if "_serialize_motor_bus" in src:
        print(f"already patched: {path}")
        return 0

    if "ROBOT_LOCK = threading.Lock()" not in src:
        print("ERROR: anchor 'ROBOT_LOCK = threading.Lock()' not found — abort.")
        return 1

    # 1) insert the wrapper right after ROBOT_LOCK is defined
    src = src.replace(
        "ROBOT_LOCK = threading.Lock()",
        "ROBOT_LOCK = threading.Lock()\n" + WRAPPER,
        1,
    )

    # 2) Wrap the follower once, anywhere after it exists. _serialize_motor_bus
    #    MUTATES the object, so every alias (local var, STATE, function args)
    #    sees the locked methods — one call is enough.
    #    Anchor on `STATE.update(` (present in every variant of this file);
    #    fall back to the original build_robot_and_pipelines assignment.
    m = re.search(r"^([ \t]*)STATE\.update\(", src, re.M)
    if m:
        indent = m.group(1)
        insert_at = m.start()
        src = (src[:insert_at]
               + f"{indent}follower = _serialize_motor_bus(follower)  # patch_bus_lock.py\n"
               + src[insert_at:])
        print("anchored on: STATE.update(")
    else:
        m = re.search(
            r"^([ \t]*)follower, joints_to_ee, ee_to_follower = .*?\n(?=[ \t]*\S)",
            src, re.M | re.S,
        )
        if not m:
            print("ERROR: no anchor found (neither 'STATE.update(' nor the follower "
                  "assignment). Apply by hand: call _serialize_motor_bus(follower) "
                  "once, right after the robot is connected.")
            return 1
        indent = m.group(1)
        src = (src[: m.end()]
               + f"{indent}follower = _serialize_motor_bus(follower)  # patch_bus_lock.py\n"
               + src[m.end():])
        print("anchored on: follower assignment")

    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    path.write_text(src)
    print(f"PATCHED {path}\nbackup  {backup}")
    print("Now restart vla_server.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
