"""Teleop sanity check — real leader drives the SIM follower, NO recording.
The sim-world equivalent of `lerobot-teleoperate` (AGENT_GUIDE 4.5): use it to
verify the leader calibration + that the sim arm tracks, before teleop_record.py.

Run (repo root, sim_server must be up):
    .venv/bin/python isaac/teleop_test.py --leader-port /dev/ttyACM0
Ctrl+C to stop. Watch the arm in the GUI or http://<ws-ip>:6060/
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import sim_config as C
from sim_client import SimClient

from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sim-host", default="127.0.0.1")
    p.add_argument("--sim-port", type=int, default=6060)
    p.add_argument("--leader-port", default="/dev/ttyACM0")
    p.add_argument("--leader-id", default="so_leader")
    p.add_argument("--calibration-dir", default=None)
    args = p.parse_args()

    sim = SimClient(args.sim_host, args.sim_port)
    print("sim server:", sim.ping())
    sim.home()

    kwargs = dict(port=args.leader_port, id=args.leader_id, use_degrees=True)
    if args.calibration_dir:
        kwargs["calibration_dir"] = Path(args.calibration_dir)
    leader = SO101Leader(SO101LeaderConfig(**kwargs))
    leader.connect()   # prompts for calibration if no file exists yet

    print("teleoperating the sim — move the leader, Ctrl+C to stop")
    t_last = time.time()
    try:
        while True:
            t0 = time.perf_counter()
            action = leader.get_action()
            sim.act(action)
            if time.time() - t_last > 1.0:
                t_last = time.time()
                print("  " + "  ".join(f"{k.split('.')[0]}={v:7.1f}" for k, v in action.items()))
            busy = time.perf_counter() - t0
            if busy < 1.0 / C.FPS:
                time.sleep(1.0 / C.FPS - busy)
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        leader.disconnect()


if __name__ == "__main__":
    main()
