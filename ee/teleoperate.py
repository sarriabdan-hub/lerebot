#!/usr/bin/env python3
"""
EE-delta teleoperation for SO-101 (vial-sort rig).

Leader joints -> FK -> EE pose -> IK -> follower joints.
Action space: translation (x, y, z) + rotation vector (wx, wy, wz) + gripper_vel.
No data is recorded. Use record.py to capture EE-delta episodes for π0 training.

Run from /home/robot/dev/lerebot/:
    conda activate lerobot
    sudo chmod 666 /dev/ttyACM*
    python ee/teleoperate.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lerobot" / "src"))

from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig
from lerobot.model.kinematics import RobotKinematics
from lerobot.processor import RobotProcessorPipeline
from lerobot.processor.converters import (
    robot_action_observation_to_transition,
    robot_action_to_transition,
    transition_to_robot_action,
)
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
from lerobot.robots.so_follower.robot_kinematic_processor import (
    EEBoundsAndSafety,
    ForwardKinematicsJointsToEE,
    InverseKinematicsEEToJoints,
)
from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig
from lerobot.types import RobotAction, RobotObservation
from lerobot.utils.robot_utils import precise_sleep
from lerobot.utils.visualization_utils import init_rerun, log_rerun_data

URDF_PATH = str(Path(__file__).parent.parent / "SO101" / "so101_new_calib.urdf")
FPS = 30

# Workspace bounds for the vial-sort table setup (metres).
# x = forward reach, y = lateral (left/right racks), z = height.
# Tuned to the taped-down workspace; tighten after the workspace sweep (Step 3).
EE_BOUNDS = {
    "min": [0.18, -0.25, 0.03],   # x<0.18 is near-singularity per workspace sweep
    "max": [0.40,  0.25, 0.32],
}
# Maximum EE displacement allowed per control step.
# 0.05 m is conservative for fine manipulation; raise if teleop feels sluggish.
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
    # Leader joints → EE absolute pose (FK)
    leader_to_ee = RobotProcessorPipeline[RobotAction, RobotAction](
        steps=[
            ForwardKinematicsJointsToEE(
                kinematics=leader_kin,
                motor_names=list(leader.bus.motors.keys()),
            ),
        ],
        to_transition=robot_action_to_transition,
        to_output=transition_to_robot_action,
    )

    # EE absolute pose → follower joints (safety clip + IK)
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

    # ── Connect ───────────────────────────────────────────────────────────────
    follower.connect()
    leader.connect()

    init_rerun(session_name="so101_ee_teleop")
    print("EE-delta teleoperation running. Ctrl+C to stop.")

    try:
        while True:
            t0 = time.perf_counter()

            robot_obs: RobotObservation = follower.get_observation()
            leader_joints: RobotAction = leader.get_action()

            # Leader joints → EE
            leader_ee: RobotAction = leader_to_ee(leader_joints)

            # EE → follower joints
            follower_joints: RobotAction = ee_to_follower((leader_ee, robot_obs))

            follower.send_action(follower_joints)

            log_rerun_data(observation=leader_ee, action=follower_joints)

            precise_sleep(max(1.0 / FPS - (time.perf_counter() - t0), 0.0))

    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        follower.disconnect()
        leader.disconnect()


if __name__ == "__main__":
    main()
