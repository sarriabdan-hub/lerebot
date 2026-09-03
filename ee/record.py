#!/usr/bin/env python3
"""
[DEPRECATED for v2 — use the official `lerobot-record` CLI instead; see ee/RECORDING_SHEET.txt.]
The CLI is the proven tool that recorded v1, has working --resume + rerecord on Thor's lerobot,
and sets per-block labels via --dataset.single_task. This script is kept only for reference.

EE-delta recording for SO-101 (vial-sort rig) — produces a dataset for π0 training.

Action space recorded: EE absolute pose (x, y, z, wx, wy, wz) + gripper_vel.
Observation recorded: EE absolute pose + 3 camera feeds.

Run from /home/robot/dev/lerebot/:
    conda activate lerobot
    sudo chmod 666 /dev/ttyACM*
    python ee/record.py

Controls during recording:
    →  save episode and continue
    ←  discard and re-record
    ESC  stop session
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lerobot" / "src"))

from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig
from lerobot.datasets.feature_utils import combine_feature_dicts
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.datasets.pipeline_features import aggregate_pipeline_dataset_features, create_initial_features
from lerobot.model.kinematics import RobotKinematics
from lerobot.processor import RobotProcessorPipeline
from lerobot.processor.converters import (
    observation_to_transition,
    robot_action_observation_to_transition,
    transition_to_observation,
    transition_to_robot_action,
)
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
from lerobot.robots.so_follower.robot_kinematic_processor import (
    EEBoundsAndSafety,
    ForwardKinematicsJointsToEE,
    InverseKinematicsEEToJoints,
)
from lerobot.scripts.lerobot_record import record_loop
from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig
from lerobot.types import RobotAction, RobotObservation
from lerobot.utils.control_utils import init_keyboard_listener
from lerobot.utils.utils import log_say
from lerobot.utils.visualization_utils import init_rerun

URDF_PATH = str(Path(__file__).parent.parent / "SO101" / "so101_new_calib.urdf")

FPS = 30
EPISODE_TIME_SEC = 30
RESET_TIME_SEC = 15
HF_REPO_ID = "sari-abdan/vial-sort-v2-ee"            # change for each session
LOCAL_ROOT = Path("/home/robot/my_local_data_v2_ee") # change for each session

# ── Per-episode labels (language conditioning) ──────────────────────────────────
# The OLD dataset (vial-sort-v1-ee) is ONE label, so the policy ignores the prompt.
# To make destination AND direction prompt-controllable we record varied destinations
# in BOTH directions and label each episode with what was actually teleoped.
#
# SCHEDULE rows = (destination_rack, position, n_episodes). The SOURCE is the OPPOSITE
# rack; vary the source SLOT every episode (source is unlabeled — the arm sees it; only
# the destination goes in the label). Keep the grammar EXACT (only rack + N vary) so the
# model generalizes the position/direction tokens. Boundary pos 6 weighted higher.
# We train on THIS fresh dataset alone (warm-start from base_v1) — the old 100 eps are at
# the old camera pose and would teach an off-pose placement, so they are NOT replayed.
TASK_TEMPLATE = "Place the red vial in position {n} of the {rack} rack."
# THIS SESSION's schedule (20-ep pilot): the two extreme destinations pos 1 & 6 in each
# direction, 5 each. Each episode is labeled with its destination. Vary the SOURCE slot per
# the table in ee/RECORDING_SHEET.txt. To record more LATER, bump SESSION (see below) — that
# writes a fresh dataset which we merge on the workstation (no risky resume API on Thor).
# Rows = (destination_rack, position, n_episodes); order = recording order.
SCHEDULE = [
    ("right", 1, 5), ("right", 6, 5),   # left rack  -> right rack, near & far
    ("left", 1, 5), ("left", 6, 5),     # right rack -> left rack,  near & far
]
EPISODE_TASKS = [TASK_TEMPLATE.format(n=n, rack=rack)
                 for rack, n, count in SCHEDULE for _ in range(count)]
NUM_EPISODES = len(EPISODE_TASKS)

EE_BOUNDS = {
    "min": [0.18, -0.25, 0.03],   # x<0.18 is near-singularity per workspace sweep
    "max": [0.40,  0.25, 0.32],
}
MAX_EE_STEP_M = 0.05


def main():
    # ── Camera configs ────────────────────────────────────────────────────────
    cameras = {
        "cam_top": OpenCVCameraConfig(
            index_or_path="/dev/v4l/by-path/platform-a80aa10000.usb-usb-0:4.2.2:1.0-video-index0",
            fps=FPS, width=640, height=480, color_mode="rgb",
        ),
        "cam_wrist": OpenCVCameraConfig(
            index_or_path="/dev/v4l/by-path/platform-a80aa10000.usb-usb-0:4.2.4:1.0-video-index0",
            fps=FPS, width=640, height=480, color_mode="rgb",
        ),
        "cam_side": RealSenseCameraConfig(
            serial_number_or_name="052622071016",
            fps=FPS, width=640, height=480, color_mode="rgb",
            warmup_s=3,
        ),
    }

    # ── Robot / teleop configs ────────────────────────────────────────────────
    follower_config = SO101FollowerConfig(
        port="/dev/ttyACM0",
        id="so_follower",
        calibration_dir=Path("/home/robot/dev/lerebot/calibration/robots/so_follower"),
        cameras=cameras,
        use_degrees=True,
    )
    leader_config = SO101LeaderConfig(
        port="/dev/ttyACM1",
        id="so_leader",
        calibration_dir=Path("/home/robot/dev/lerebot/calibration/teleoperators/so_leader"),
    )

    follower = SO101Follower(follower_config)
    leader = SO101Leader(leader_config)

    # ── Kinematics solvers ────────────────────────────────────────────────────
    follower_kin = RobotKinematics(
        urdf_path=URDF_PATH,
        target_frame_name="gripper_frame_link",
        joint_names=list(follower.bus.motors.keys()),
    )
    leader_kin = RobotKinematics(
        urdf_path=URDF_PATH,
        target_frame_name="gripper_frame_link",
        joint_names=list(leader.bus.motors.keys()),
    )

    # ── Processing pipelines ──────────────────────────────────────────────────
    # Leader joints → EE action
    leader_to_ee = RobotProcessorPipeline[tuple[RobotAction, RobotObservation], RobotAction](
        steps=[
            ForwardKinematicsJointsToEE(
                kinematics=leader_kin,
                motor_names=list(leader.bus.motors.keys()),
            ),
        ],
        to_transition=robot_action_observation_to_transition,
        to_output=transition_to_robot_action,
    )

    # Follower joints → EE observation
    follower_joints_to_ee = RobotProcessorPipeline[RobotObservation, RobotObservation](
        steps=[
            ForwardKinematicsJointsToEE(
                kinematics=follower_kin,
                motor_names=list(follower.bus.motors.keys()),
            ),
        ],
        to_transition=observation_to_transition,
        to_output=transition_to_observation,
    )

    # EE action → follower joints
    ee_to_follower = RobotProcessorPipeline[tuple[RobotAction, RobotObservation], RobotAction](
        steps=[
            EEBoundsAndSafety(
                end_effector_bounds=EE_BOUNDS,
                max_ee_step_m=MAX_EE_STEP_M,
            ),
            InverseKinematicsEEToJoints(
                kinematics=follower_kin,
                motor_names=list(follower.bus.motors.keys()),
                initial_guess_current_joints=True,
            ),
        ],
        to_transition=robot_action_observation_to_transition,
        to_output=transition_to_robot_action,
    )

    # ── Dataset (resume if it already exists, else create) ──────────────────────
    if LOCAL_ROOT.exists():
        print(f"Resuming existing dataset at {LOCAL_ROOT}")
        dataset = LeRobotDataset.resume(
            repo_id=HF_REPO_ID,
            root=LOCAL_ROOT,
            image_writer_threads=4,
        )
    else:
        print(f"Creating new dataset at {LOCAL_ROOT}")
        dataset = LeRobotDataset.create(
            repo_id=HF_REPO_ID,
            root=LOCAL_ROOT,
            fps=FPS,
            features=combine_feature_dicts(
                aggregate_pipeline_dataset_features(
                    pipeline=leader_to_ee,
                    initial_features=create_initial_features(action=leader.action_features),
                    use_videos=True,
                ),
                aggregate_pipeline_dataset_features(
                    pipeline=follower_joints_to_ee,
                    initial_features=create_initial_features(observation=follower.observation_features),
                    use_videos=True,
                ),
            ),
            robot_type=follower.name,
            use_videos=True,
            image_writer_threads=4,
        )

    # ── Connect ───────────────────────────────────────────────────────────────
    leader.connect()
    follower.connect()

    listener, events = init_keyboard_listener()
    init_rerun(session_name="so101_ee_record")

    # Resume from the last saved episode; cap this run at MAX_THIS_SESSION.
    start_idx = dataset.num_episodes
    end_idx = min(NUM_EPISODES, start_idx + MAX_THIS_SESSION)
    if start_idx >= NUM_EPISODES:
        print(f"All {NUM_EPISODES} scheduled episodes already recorded. Add more rows to SCHEDULE.")
        leader.disconnect(); follower.disconnect(); listener.stop(); dataset.finalize()
        return
    print(f"Already have {start_idx} episodes. Recording {start_idx}..{end_idx - 1} "
          f"({end_idx - start_idx} this session) of {NUM_EPISODES} total.")

    try:
        episode_idx = start_idx
        while episode_idx < end_idx and not events["stop_recording"]:
            task = EPISODE_TASKS[episode_idx]   # this episode's destination label
            log_say(f"Recording episode {episode_idx + 1} of {NUM_EPISODES}: {task}")

            record_loop(
                robot=follower,
                events=events,
                fps=FPS,
                teleop=leader,
                dataset=dataset,
                control_time_s=EPISODE_TIME_SEC,
                single_task=task,
                display_data=True,
                teleop_action_processor=leader_to_ee,
                robot_action_processor=ee_to_follower,
                robot_observation_processor=follower_joints_to_ee,
            )

            if not events["stop_recording"] and (
                episode_idx < end_idx - 1 or events["rerecord_episode"]
            ):
                log_say("Reset — put the vial in the SOURCE rack (opposite the destination "
                        "you'll hear next), at a NEW slot")
                record_loop(
                    robot=follower,
                    events=events,
                    fps=FPS,
                    teleop=leader,
                    control_time_s=RESET_TIME_SEC,
                    single_task=task,
                    display_data=True,
                    teleop_action_processor=leader_to_ee,
                    robot_action_processor=ee_to_follower,
                    robot_observation_processor=follower_joints_to_ee,
                )

            if events["rerecord_episode"]:
                log_say("Re-recording episode")
                events["rerecord_episode"] = False
                events["exit_early"] = False
                dataset.clear_episode_buffer()
                continue

            dataset.save_episode()
            episode_idx += 1

    finally:
        log_say("Stop recording")
        leader.disconnect()
        follower.disconnect()
        listener.stop()
        dataset.finalize()

    print(f"Done. {episode_idx} episodes saved to {LOCAL_ROOT}")


if __name__ == "__main__":
    main()
