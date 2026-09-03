"""
Record the vial-sort pilot IN SIM — runs in the NORMAL lerobot env (py3.12),
talking to sim_server.py (which runs in the isaac-venv, see README).

The real SO-101 LEADER arm (USB on this WS) drives the simulated follower; the
3 sim cameras + sim joint state are written to a LeRobotDataset with the SAME
keys as the real rig, following ee/initial_fable_v5.txt (or --v4 for the
original single-red-vial task). Scene setup + homing are automatic.

Dataset schema (joint-space raw, like the real recordings — convert to EE
afterwards with the existing ee/convert_dataset.py flow):
    action / observation.state    float32 (6,)  joints deg + gripper 0..100
    observation.images.cam_{top,wrist,side}   video 480x640x3 @30

Keys: -> save episode   <- re-record   ESC stop session

Run (terminal 1: sim server in isaac-venv; terminal 2, repo root):
    uv run python isaac/teleop_record.py --leader-port /dev/ttyACM0 \
        --root ~/sim_data_v5_pilot --repo-id sari-abdan/vial-sort-v5-sim-pilot
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np

import sim_config as C
from sheet import make_v4_episodes, parse_sheet
from sim_client import SimClient

from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig
from lerobot.common.control_utils import init_keyboard_listener
from lerobot.utils.utils import log_say

STATE_NAMES = [f"{j}.pos" for j in C.JOINT_NAMES]


def start_stdin_keys(events: dict) -> None:
    """SSH-friendly controls: pynput needs an X display, so over SSH the arrow keys
    do nothing. This reads raw stdin instead (works in any terminal):
      s or ->  save episode | r or <-  re-record | q or ESC  stop session."""
    import termios
    import threading
    import tty

    if not sys.stdin.isatty():
        return

    def reader():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while not events["stop_recording"]:
                ch = sys.stdin.read(1)
                if ch == "\x1b":                      # ESC or arrow-key escape seq
                    rest = sys.stdin.read(1) if sys.stdin.readable() else ""
                    if rest == "[":
                        code = sys.stdin.read(1)
                        if code == "C":               # right arrow
                            events["exit_early"] = True
                        elif code == "D":             # left arrow
                            events["rerecord_episode"] = True
                            events["exit_early"] = True
                    else:                             # bare ESC
                        events["stop_recording"] = True
                        events["exit_early"] = True
                elif ch in ("s", "S"):
                    events["exit_early"] = True
                elif ch in ("r", "R"):
                    events["rerecord_episode"] = True
                    events["exit_early"] = True
                elif ch in ("q", "Q"):
                    events["stop_recording"] = True
                    events["exit_early"] = True
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    threading.Thread(target=reader, daemon=True).start()

FEATURES = {
    "action": {"dtype": "float32", "shape": (6,), "names": STATE_NAMES},
    "observation.state": {"dtype": "float32", "shape": (6,), "names": STATE_NAMES},
    **{
        f"observation.images.{cam}": {
            "dtype": "video",
            "shape": (C.CAM_HEIGHT, C.CAM_WIDTH, 3),
            "names": ["height", "width", "channels"],
        }
        for cam in ("cam_top", "cam_wrist", "cam_side")
    },
}


def vec(d: dict[str, float]) -> np.ndarray:
    return np.array([d[k] for k in STATE_NAMES], dtype=np.float32)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sim-host", default="127.0.0.1")
    p.add_argument("--sim-port", type=int, default=6060)
    p.add_argument("--leader-port", default="/dev/ttyACM0")
    p.add_argument("--leader-id", default="so_leader")
    p.add_argument("--calibration-dir", default=None)
    p.add_argument("--repo-id", default="sari-abdan/vial-sort-v5-sim-pilot")
    p.add_argument("--root", default=str(Path.home() / "sim_data_v5_pilot"))
    p.add_argument("--sheet", default=None)
    p.add_argument("--v4", action="store_true",
                   help="record the ORIGINAL v4 task (single red vial) instead of the v5 sheet")
    p.add_argument("--v4-eps-per-dest", type=int, default=30)
    p.add_argument("--episode-time-s", type=float, default=40.0)
    p.add_argument("--max-episodes", type=int, default=25)
    args = p.parse_args()

    sim = SimClient(args.sim_host, args.sim_port)
    info = sim.ping()
    print(f"sim server ok: {info}")

    if args.v4:
        episodes = make_v4_episodes(n_per_dest=args.v4_eps_per_dest)
        print(f"v4 mode: {len(episodes)} single-red-vial episodes, interleaved destinations")
    else:
        episodes = parse_sheet(args.sheet or C.SHEET_PATH)

    leader_kwargs = dict(port=args.leader_port, id=args.leader_id, use_degrees=True)
    if args.calibration_dir:
        leader_kwargs["calibration_dir"] = Path(args.calibration_dir)
    leader = SO101Leader(SO101LeaderConfig(**leader_kwargs))
    leader.connect()

    root = Path(args.root)
    if root.exists():
        print(f"Resuming dataset at {root}")
        dataset = LeRobotDataset.resume(repo_id=args.repo_id, root=root, image_writer_threads=4)
    else:
        print(f"Creating dataset at {root}")
        dataset = LeRobotDataset.create(
            repo_id=args.repo_id, root=root, fps=C.FPS, features=FEATURES,
            robot_type="so101_follower_sim", use_videos=True, image_writer_threads=4,
        )

    listener, events = init_keyboard_listener()
    start_stdin_keys(events)   # terminal keys (s/r/q) — the only controls over SSH
    print("Controls: s or -> save | r or <- re-record | q or ESC stop")
    start = dataset.num_episodes
    end = min(len(episodes), start + args.max_episodes)
    if start >= len(episodes):
        print(f"All {len(episodes)} episodes recorded already.")
        leader.disconnect()
        if listener is not None:
            listener.stop()
        dataset.finalize()
        return
    print(f"Have {start} episodes. Recording {start}..{end - 1} of {len(episodes)}.")

    try:
        ep_idx = start
        while ep_idx < end and not events["stop_recording"]:
            ep_info = sim.reset(episode=ep_idx, v4=args.v4)  # vials + home, automatic
            task = ep_info["task"]
            log_say(f"Episode {ep_idx + 1} of {len(episodes)}: {task}")
            print(f"  scene L:{ep_info['left']} R:{ep_info['right']} -> {ep_info['dest']}")
            print("  match the leader to the home pose, then start moving.")

            events["exit_early"] = False
            n_frames = int(args.episode_time_s * C.FPS)
            for _ in range(n_frames):
                if events["exit_early"] or events["rerecord_episode"] or events["stop_recording"]:
                    break
                t0 = time.perf_counter()
                action = leader.get_action()
                sim.act(action)
                state, imgs = sim.obs()
                frame = {
                    "action": vec(action),
                    "observation.state": vec(state),
                    "task": task,
                    **{f"observation.images.{k}": v for k, v in imgs.items()},
                }
                dataset.add_frame(frame)
                busy = time.perf_counter() - t0
                if busy < 1.0 / C.FPS:
                    time.sleep(1.0 / C.FPS - busy)

            if events["rerecord_episode"]:
                log_say("Re-recording episode")
                events["rerecord_episode"] = False
                events["exit_early"] = False
                dataset.clear_episode_buffer()
                continue
            if events["stop_recording"]:
                dataset.clear_episode_buffer()
                break

            dataset.save_episode()
            ep_idx += 1
    finally:
        log_say("Stop recording")
        leader.disconnect()
        if listener is not None:  # None in headless envs (no pynput)
            listener.stop()
        dataset.finalize()

    print(f"Done. Dataset now has {ep_idx} episodes at {root}")
    print("Next: joint->EE convert (ee/convert_dataset.py flow), paraphrase, train per PLAN_FABLE.")


if __name__ == "__main__":
    main()
