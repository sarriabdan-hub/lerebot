"""
Single source of truth for the vial-sort sim: geometry, cameras, joints, colors.

Everything mirrors the REAL **V4** rig, calibrated against actual v4 dataset
frames (data/vial-sort-v4-merged-ee, cam_top/cam_side first frames):
- SO-101 arm behind the middle gap between two BLACK, ELEVATED RAIL-style
  6-slot test-tube racks that form a slight V (chevron) opening toward the arm
  (slot 1 = near end at the gap, slot 6 far).
- NO bin (v4 predates it). The v5 bin exists behind --with-bin / with_bin=True.
- v4 vials: TALL red test tubes (~0.12 m). Other colors kept for v5 sheets.
- 3 cameras named exactly like the real dataset keys: cam_top (overhead),
  cam_wrist (gripper), cam_side (RealSense IN FRONT, looking back at the arm)
  (640x480 @ 30 fps).

Coordinate frame: arm base_link at the origin ON the table top (z=0),
+X pointing away from the arm toward the racks, +Y to the arm's LEFT, +Z up.
All numbers are meters / degrees unless stated. Values marked TUNE are eyeballed
to match the real scene — adjust after looking at smoke_test.py renders next to
the real reference frames (ee/extract_ref_frame.py output).
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
URDF_PATH = str(REPO_ROOT / "SO101" / "so101_new_calib.urdf")
SHEET_PATH = str(REPO_ROOT / "ee" / "initial_fable_v5.txt")

FPS = 30                    # control + camera rate, same as real recording
PHYSICS_DT = 1.0 / 120.0    # physics substeps
DECIMATION = 4              # 120 Hz physics / 4 = 30 Hz control

# ── Joints ───────────────────────────────────────────────────────────────────
# lerobot motor order (leader.get_action() key order == follower bus order)
JOINT_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
BODY_JOINTS = JOINT_NAMES[:5]           # degrees on the real bus (use_degrees=True)
# gripper is RANGE_0_100 on the real bus (0=closed .. 100=open); mapped to the
# URDF gripper joint limits linearly at runtime (scene.py reads the limits).

# Home pose copied from ee/vla_server.py HOME_POSE (mean first-frame of v4-ee data).
HOME_POSE_DEG = {
    "shoulder_pan": -4.9,
    "shoulder_lift": -106.2,
    "elbow_flex": 96.4,
    "wrist_flex": -102.3,
    "wrist_roll": -163.0,
}
HOME_GRIPPER_0100 = 3.0

# PD drive for the sim servos (STS3215-ish behavior).  TUNE if tracking is
# sluggish (raise stiffness) or oscillates (raise damping).
DRIVE_STIFFNESS = 600.0
DRIVE_DAMPING = 60.0
GRIPPER_STIFFNESS = 200.0
GRIPPER_DAMPING = 20.0

# ── Table ────────────────────────────────────────────────────────────────────
TABLE_SIZE = (1.20, 0.90, 0.75)                 # x, y, thickness-to-floor
TABLE_TOP_Z = 0.0                               # table surface = world z 0
TABLE_CENTER = (0.25, 0.0, -TABLE_SIZE[2] / 2)  # slab below the surface

# ── Racks — V4-REAL layout (calibrated against actual v4 dataset frames) ─────
# Ground truth = first frames of data/vial-sort-v4-merged-ee (cam_top file-000 +
# cam_side file-000). The REAL racks are NOT low well-blocks: they are BLACK,
# ELEVATED RAIL-style test-tube racks — a base bar on the table, end legs, and a
# TOP RAIL with 6 round holes at ~0.10 m; the vial stands on the base bar and is
# laterally held by the rail hole. And the two racks are NOT parallel: they form
# a slight V (chevron) opening toward the arm, near ends ~0.28 m out, gap between
# the near ends in front of the arm.
#
# All poses below are estimated from the frames (pixel measurements) — marked
# TUNE. CALIBRATION LOOP: run smoke_test.py, compare its cam_top/cam_side renders
# side-by-side with scratchpad v4_top.png / v4_side.png (or re-extract:
#   ffmpeg -i data/vial-sort-v4-merged-ee/videos/observation.images.cam_top/chunk-000/file-000.mp4 -vframes 1 top.png)
# and nudge SLOT1 xy / yaw until rack outlines overlay.
import math

SLOT_PITCH = 0.036          # slot-center spacing along the rack axis
N_SLOTS = 6

# Per-rack pose: slot-1 center (near end, by the middle gap) + yaw of the rack
# axis (0 deg = straight away from the arm, +X). Estimated from v4_top.png:
# LEFT rack clearly diagonal (~-38 deg), RIGHT rack near-straight (~+8 deg).
# NAMING/TUNE: "left/right" follow the v4 PROMPT convention. Verify after the
# first render: in cam_side the red vial of episode 0 (source = LEFT slot 1)
# must appear in the image-LEFT rack, like the real v4_side.png. If mirrored,
# swap the two entries below.
# Scale constraint: the arm DID place at slot 6 in v4, so slot 6 must sit inside
# the EE workspace (x <= 0.40) -> slot 1 ~0.21 m out (matches ee/record.py bounds).
# CALIBRATED against real v4 frames (scratchpad real_cam_top/side.png, 2026-07-08):
# real cam_side shows the two racks near-SYMMETRIC flanking the centered arm (red
# source vial in the image-LEFT rack), and real cam_top shows a shallow V whose
# vertex is near the arm and opens AWAY (+X), each rack ~42 deg off the +X axis so
# it reads broadside to the front cam. "left" = -Y (arm's right) so it lands
# image-LEFT in cam_side, matching the real red-vial side. Previous right yaw (+8)
# made that rack radiate straight out (end-on/tiny in cam_side) -> the asymmetry.
RACK_POSE = {
    "left":  {"slot1": (0.20, -0.035), "yaw_deg": -42.0},   # -Y, image-LEFT in cam_side
    "right": {"slot1": (0.20, +0.035), "yaw_deg": +42.0},   # +Y, image-RIGHT in cam_side
}

# Rail-rack geometry (from v4_side.png proportions)
RACK_BASE_H = 0.012         # base bar the vial stands on
RACK_BASE_W = 0.030         # base bar width
RACK_RAIL_Z = 0.100         # TOP RAIL height above table  (TUNE)
RACK_RAIL_T = 0.010         # rail thickness (z)
RACK_HOLE = 0.022           # rail hole opening (square approx of the round hole)
RACK_RAIL_BAR = 0.007       # width of the rail material between/around holes
RACK_LEG_T = 0.008          # end-leg thickness
RACK_COLOR = (0.08, 0.08, 0.08)   # BLACK plastic (real racks), not white

def rack_axis(rack: str) -> tuple[float, float]:
    yaw = math.radians(RACK_POSE[rack]["yaw_deg"])
    return (math.cos(yaw), math.sin(yaw))

def slot_center(rack: str, slot: int) -> tuple[float, float, float]:
    """World-frame point where the VIAL BASE sits for a slot (on the base bar).
    rack in {left,right}, slot 1..6 (slot 1 = near end, by the middle gap)."""
    x1, y1 = RACK_POSE[rack]["slot1"]
    ax, ay = rack_axis(rack)
    d = (slot - 1) * SLOT_PITCH
    return (x1 + ax * d, y1 + ay * d, TABLE_TOP_Z + RACK_BASE_H)

# ── Bin (v5 pilot only — the V4 scene has NO bin; default is OFF, see scene.py) ──
WITH_BIN_DEFAULT = False                 # v4 replica. Flip / pass with_bin=True for v5.
BIN_CENTER = (0.24, 0.27, TABLE_TOP_Z)   # TUNE to the real taped position (v5)
BIN_INNER = (0.11, 0.11)                 # inner x, y
BIN_WALL_T = 0.006
BIN_WALL_H = 0.075

# ── Vials ────────────────────────────────────────────────────────────────────
# Real v4 vial = TALL red-capped test tube (~0.12 m), not a squat 68 mm cylinder
# (see v4_side.png: the tube spans base bar -> above the rail).
VIAL_RADIUS = 0.0085
VIAL_HEIGHT = 0.140         # Sari 2026-07-09: 0.120 too short to grip above the rail,
                            # 0.155 unrealistic; settled at 0.14.

# Per-slot "egg-cup" socket on the base bar (Sari 2026-07-09: a grabbed-then-released
# vial shifted off its slot): 4 low nubs around each slot base keep the vial seated.
SLOT_CUP_GAP = 0.0205       # opening between opposing nubs (vial dia 0.017 + clearance)
SLOT_CUP_T = 0.004          # nub thickness
SLOT_CUP_H = 0.010          # nub height above the base bar
SLOT_CUP_L = 0.016          # nub length

# Sari 2026-07-09, SIM PILOT ONLY (temporary): never stage two vials in ADJACENT
# slots of the same rack ("directly behind each other" along the rack axis — they
# get hit during the grasp). Target always placed; distractors that would violate
# adjacency stay parked. Flip False to restore exact sheet fidelity.
SKIP_ADJACENT_DISTRACTORS = True
VIAL_MASS = 0.014
VIALS_PER_COLOR = 3          # pool size; a scene never needs more than 3 of a color
VIAL_PARK = (-0.5, 0.0, 0.2)  # off-table parking spot for unused vials (staggered)
# NOTE: v4 dataset episodes use RED only; the other colors exist for v5 sheets.

# Sheet letters -> (name, RGB).  Colors chosen for max separation like the real set.
VIAL_COLORS = {
    "R": ("red",          (0.85, 0.08, 0.08)),
    "C": ("cyan",         (0.10, 0.75, 0.85)),
    "G": ("dark_green",   (0.05, 0.35, 0.10)),
    "P": ("light_purple", (0.72, 0.58, 0.90)),
}

# ── Cameras (names == real dataset keys; 640x480 @ 30) ──────────────────────
CAM_WIDTH, CAM_HEIGHT = 640, 480

# Static cams: defined by eye + look-at target (applied with
# Camera.set_world_poses_from_view). Calibrated against the REAL v4 first frames
# (v4_top.png / v4_side.png) — the previous values were wrong in kind, not just
# in degree: the side cam was placed to the arm's RIGHT, but in the real rig the
# RealSense sits IN FRONT of the scene looking BACK at the arm (v4_side.png shows
# the arm head-on with the racks flanking it and the gap in the middle).
CAM_TOP = {  # steep overhead, mounted to the arm's +Y side (like the real rig):
    # real cam_top has the ARM on image-RIGHT and racks on image-LEFT. A pure
    # straight-down eye gives a degenerate/ambiguous roll (rendered mirrored), so
    # offset the eye in +Y and look down+toward -Y to define the orientation.
    "eye": (0.24, 0.42, 0.50),     # TUNE: above + to the arm's LEFT side, steep down
    "target": (0.24, -0.02, 0.0),
    "focal_length_mm": 14.0,
}
CAM_SIDE = {  # the RealSense: IN FRONT of the racks, looking back at the arm
    "eye": (0.72, 0.02, 0.20),     # TUNE: beyond the rack far ends, near table axis
    "target": (0.02, 0.0, 0.12),   # the arm's torso
    "focal_length_mm": 14.0,
}
# Wrist cam: rigidly attached to the gripper link, looking at the fingers.
# CALIBRATED 2026-07-09 by 3 probe rounds (scratchpad probe_wrist*.py, 22 candidates):
# the original quat stared at the SIDE of the gripper body ("the gripper doesn't have a
# camera"); plain identity looked down but the fingers were out of frame. This pose =
# identity rotation (ROS convention) shifted back/left/up so BOTH finger plates sit at
# the image bottom with the workspace ahead — Sari's requirement: "show the 2 fingers".
# FINAL (probe round 6, 2026-07-09): URDF says fingertips sit at z=-0.098 in
# gripper_link frame -> view dir must be -Z (all earlier "identity" poses looked
# BACKWARD at the arm's own leg). This pose = outboard on the +Y side, view -Z
# tilted 25 deg: BOTH fingers rise from image-bottom in a V with the scene beyond —
# same framing as the real wrist cam (which shows ceiling at home, vial at grasp).
CAM_WRIST = {
    "parent_link": "gripper_link",
    "offset_pos": (0.0, 0.06, -0.02),            # in gripper_link frame
    "offset_rot_wxyz": (0.2164, 0.9763, 0.0, 0.0),   # Rx(155deg)
    "focal_length_mm": 12.0,
}

# EE safety bounds (same as real recording, ee/record.py) — used by eval_pi05 --ee
EE_BOUNDS = {"min": [0.18, -0.25, 0.03], "max": [0.40, 0.25, 0.32]}
MAX_EE_STEP_M = 0.05
