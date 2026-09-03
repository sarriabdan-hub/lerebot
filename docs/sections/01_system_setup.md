# 1. System Setup and Assembly

The physical rig was **assembled and calibrated by the author**.

## Hardware
- **Arm:** SO-101 six-DOF manipulator in a **leader–follower** configuration — the
  operator moves the leader arm and the follower mirrors it (used for teleoperated
  data collection).
- **Compute:** NVIDIA **Jetson Thor** — runs camera capture, policy inference, and
  motor control on-device.
- **Cameras** (all 640×480 @ 30 fps): overhead **top**, **wrist**, and a
  front-facing Intel **RealSense D435i** (**side**).
- **Workspace:** two six-slot tube racks arranged **diagonally** to the arm, with a
  **bin** on the left for discards.

## Spatial convention (defined from the side camera)
To remove ambiguity, all references are read from the side-camera image:
- **left rack** = the rack on the left of that image (nearest the bin);
- **right rack** = the rack on the right;
- **slots 1–6** = counted left-to-right in the image.

## Assembly / calibration steps
- Mounting and pinning the three cameras (fixed positions).
- Fixing the rack and bin footprints.
- Calibrating the leader and follower arms.
- Verifying the serial motor bus.
- A **safety watchdog** monitors per-motor temperature and current and cuts torque
  after repeated limit violations.

*Figures:* `setup_side.png`, `cameras.png`.
