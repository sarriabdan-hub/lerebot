"""
Isaac Lab scene for the vial-sort task: table, SO-101 (from the repo URDF),
two 6-slot racks, bin, colored vial pool, and the 3 named cameras.

IMPORTANT: this module imports isaaclab, so the entry script must launch the
SimulationApp FIRST (via isaaclab.app.AppLauncher) and only then import this
module.  See teleop_record.py / smoke_test.py for the pattern.

Targeted API: Isaac Sim 5.x + Isaac Lab 2.x (pip workflow).  Field names in
Urdf/JointDrive configs occasionally shift between Isaac Lab minor versions —
if a spawn fails, check the matching isaaclab.sim.spawners docs for your pin.
"""

from __future__ import annotations

import math

import numpy as np
import torch

import isaaclab.sim as sim_utils
from isaaclab.actuators import ImplicitActuatorCfg
from isaaclab.assets import Articulation, ArticulationCfg, RigidObject, RigidObjectCfg
from isaaclab.sensors import Camera, CameraCfg
from isaaclab.sim import SimulationContext

import sim_config as C
from sheet import Episode

DEG = math.pi / 180.0


# ─────────────────────────────────────────────────────────────────────────────
# Static scenery (plain USD prims, no handles needed afterwards)
# ─────────────────────────────────────────────────────────────────────────────

def _static_box(path: str, size, pos, color=(0.55, 0.55, 0.55), yaw_deg: float = 0.0):
    cfg = sim_utils.CuboidCfg(
        size=tuple(size),
        collision_props=sim_utils.CollisionPropertiesCfg(),
        visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=color, roughness=0.6),
    )
    half = math.radians(yaw_deg) / 2.0
    cfg.func(path, cfg, translation=tuple(pos),
             orientation=(math.cos(half), 0.0, 0.0, math.sin(half)))


def _spawn_table():
    _static_box("/World/Table", C.TABLE_SIZE, C.TABLE_CENTER, color=(0.82, 0.78, 0.72))


def _spawn_rack(name: str, rack: str):
    """V4-real ELEVATED RAIL rack (black): base bar on the table + end legs + a
    top rail grid with 6 openings at C.RACK_RAIL_Z. The vial stands on the base
    bar, held laterally by the rail opening — like the real test-tube racks in
    v4_side.png. The whole rack is yawed by C.RACK_POSE[rack]['yaw_deg'] (the
    real racks form a V), so every element is placed in RACK-LOCAL coordinates
    (local x = along the rack from slot 1, local y = perpendicular) and rotated
    into the world.
    """
    x1, y1 = C.RACK_POSE[rack]["slot1"]
    yaw = C.RACK_POSE[rack]["yaw_deg"]
    ax, ay = C.rack_axis(rack)          # unit vector along the rack
    px, py = -ay, ax                    # unit vector perpendicular (local +y)
    color = C.RACK_COLOR

    def place(sub: str, local_x: float, local_y: float, z_center: float, size_local):
        wx = x1 + ax * local_x + px * local_y
        wy = y1 + ay * local_x + py * local_y
        _static_box(f"/World/{name}/{sub}", size_local, (wx, wy, z_center), color, yaw_deg=yaw)

    P, N = C.SLOT_PITCH, C.N_SLOTS
    rack_mid = (N - 1) * P / 2
    base_len = N * P + 2 * C.RACK_LEG_T
    top_z = C.TABLE_TOP_Z + C.RACK_RAIL_Z + C.RACK_RAIL_T / 2
    rail_w = C.RACK_HOLE + 2 * C.RACK_RAIL_BAR   # rail outer width

    # base bar the vials stand on
    place("base", rack_mid, 0.0, C.TABLE_TOP_Z + C.RACK_BASE_H / 2,
          (base_len, C.RACK_BASE_W, C.RACK_BASE_H))
    # end legs up to the rail
    leg_h = C.RACK_RAIL_Z + C.RACK_RAIL_T
    for lx, sub in ((-P / 2 - C.RACK_LEG_T / 2, "leg_near"),
                    ((N - 0.5) * P + C.RACK_LEG_T / 2, "leg_far")):
        place(sub, lx, 0.0, C.TABLE_TOP_Z + leg_h / 2, (C.RACK_LEG_T, C.RACK_BASE_W, leg_h))
    # top rail: two long side bars + cross bars => N square openings
    for side in (-1, 1):
        place(f"rail_{'l' if side > 0 else 'r'}", rack_mid,
              side * (C.RACK_HOLE + C.RACK_RAIL_BAR) / 2, top_z,
              (N * P, C.RACK_RAIL_BAR, C.RACK_RAIL_T))
    for i in range(N + 1):
        place(f"rail_cross_{i}", -P / 2 + i * P, 0.0, top_z,
              (C.RACK_RAIL_BAR, rail_w, C.RACK_RAIL_T))
    # per-slot "egg-cup": 4 low nubs around each slot base so a placed/released
    # vial stays seated instead of sliding off its slot
    cup_z = C.TABLE_TOP_Z + C.RACK_BASE_H + C.SLOT_CUP_H / 2
    off = (C.SLOT_CUP_GAP + C.SLOT_CUP_T) / 2
    for i in range(N):
        sx = i * P
        place(f"cup_{i}_xn", sx - off, 0.0, cup_z, (C.SLOT_CUP_T, C.SLOT_CUP_L, C.SLOT_CUP_H))
        place(f"cup_{i}_xp", sx + off, 0.0, cup_z, (C.SLOT_CUP_T, C.SLOT_CUP_L, C.SLOT_CUP_H))
        place(f"cup_{i}_yn", sx, -off, cup_z, (C.SLOT_CUP_L, C.SLOT_CUP_T, C.SLOT_CUP_H))
        place(f"cup_{i}_yp", sx, +off, cup_z, (C.SLOT_CUP_L, C.SLOT_CUP_T, C.SLOT_CUP_H))


def _spawn_bin():
    bx, by, bz = C.BIN_CENTER
    ix, iy = C.BIN_INNER
    t, h = C.BIN_WALL_T, C.BIN_WALL_H
    color = (0.25, 0.25, 0.28)  # dark bin
    _static_box("/World/Bin/floor", (ix + 2 * t, iy + 2 * t, t), (bx, by, bz + t / 2), color)
    wz = bz + t + h / 2
    _static_box("/World/Bin/wall_xn", (t, iy + 2 * t, h), (bx - (ix + t) / 2, by, wz), color)
    _static_box("/World/Bin/wall_xp", (t, iy + 2 * t, h), (bx + (ix + t) / 2, by, wz), color)
    _static_box("/World/Bin/wall_yn", (ix + 2 * t, t, h), (bx, by - (iy + t) / 2, wz), color)
    _static_box("/World/Bin/wall_yp", (ix + 2 * t, t, h), (bx, by + (iy + t) / 2, wz), color)


# ─────────────────────────────────────────────────────────────────────────────
# Robot
# ─────────────────────────────────────────────────────────────────────────────

def _urdf_joint_limits() -> dict[str, tuple[float, float]]:
    """Joint limits (rad) parsed from the URDF, for clamping poses at cfg time."""
    import xml.etree.ElementTree as ET

    limits = {}
    for joint in ET.parse(C.URDF_PATH).getroot().iter("joint"):
        lim = joint.find("limit")
        if lim is not None and "lower" in lim.attrib:
            limits[joint.attrib["name"]] = (float(lim.attrib["lower"]), float(lim.attrib["upper"]))
    return limits


def clamp_to_limits(joint: str, value_rad: float, margin: float = 0.005) -> float:
    lo, hi = _urdf_joint_limits()[joint]
    return min(max(value_rad, lo + margin), hi - margin)


def _so101_cfg() -> ArticulationCfg:
    # The real bus's calibrated degrees can exceed the URDF's nominal limits by a
    # few degrees (e.g. shoulder_lift -106.2 vs ±100) — clamp for the sim.
    home_rad = {j: clamp_to_limits(j, v * DEG) for j, v in C.HOME_POSE_DEG.items()}
    home_rad["gripper"] = 0.5  # rough mid; corrected against limits after reset
    return ArticulationCfg(
        prim_path="/World/Robot",
        spawn=sim_utils.UrdfFileCfg(
            asset_path=C.URDF_PATH,
            fix_base=True,
            merge_fixed_joints=False,   # keep gripper_frame_link for FK parity
            # convex_hull (the default) closes the concave gap between the gripper
            # fingers (hull of a forked jaw = a solid wedge), so vials "phase"
            # through and can never be grasped. Decomposition keeps the gap open.
            collider_type="convex_decomposition",
            joint_drive=sim_utils.UrdfConverterCfg.JointDriveCfg(
                target_type="position",
                gains=sim_utils.UrdfConverterCfg.JointDriveCfg.PDGainsCfg(
                    stiffness=C.DRIVE_STIFFNESS, damping=C.DRIVE_DAMPING
                ),
            ),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(max_depenetration_velocity=1.0),
            articulation_props=sim_utils.ArticulationRootPropertiesCfg(
                enabled_self_collisions=False, solver_position_iteration_count=16
            ),
        ),
        init_state=ArticulationCfg.InitialStateCfg(pos=(0.0, 0.0, C.TABLE_TOP_Z), joint_pos=home_rad),
        actuators={
            "body": ImplicitActuatorCfg(
                joint_names_expr=[j for j in C.BODY_JOINTS],
                stiffness=C.DRIVE_STIFFNESS, damping=C.DRIVE_DAMPING,
            ),
            "gripper": ImplicitActuatorCfg(
                joint_names_expr=["gripper"],
                stiffness=C.GRIPPER_STIFFNESS, damping=C.GRIPPER_DAMPING,
                # Without an effort cap the position drive squeezes with unbounded
                # force when commanded past the vial's width -> the vial pops
                # THROUGH a finger collider ("phasing into one finger"). Real
                # ST3215 stalls at ~3 Nm; cap the sim likewise so it pinches.
                effort_limit_sim=2.0,
            ),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# The scene
# ─────────────────────────────────────────────────────────────────────────────

class VialSortScene:
    """Owns the sim context, robot, vial pool and cameras.

    Degrees in / degrees out on every public method, matching the real lerobot
    bus (`use_degrees=True`); gripper is 0..100 like RANGE_0_100.
    """

    def __init__(self, sim: SimulationContext, with_bin: bool = C.WITH_BIN_DEFAULT):
        self.sim = sim
        self.device = sim.device

        # scenery
        light = sim_utils.DomeLightCfg(intensity=800.0, color=(1.0, 1.0, 1.0))
        light.func("/World/DomeLight", light)
        sun = sim_utils.DistantLightCfg(intensity=2500.0, angle=2.0, color=(1.0, 0.98, 0.95))
        sun.func("/World/Sun", sun, orientation=(0.924, 0.30, 0.20, 0.0))
        _spawn_table()
        _spawn_rack("RackLeft", "left")
        _spawn_rack("RackRight", "right")
        if with_bin:  # DEFAULT OFF (v4 replica has no bin); pass --with-bin for v5 scenes
            _spawn_bin()

        # robot
        self.robot = Articulation(_so101_cfg())

        # vial pool: VIALS_PER_COLOR rigid cylinders per color, parked off-table
        self.vials: dict[str, list[RigidObject]] = {}
        for letter, (cname, rgb) in C.VIAL_COLORS.items():
            self.vials[letter] = []
            for k in range(C.VIALS_PER_COLOR):
                cfg = RigidObjectCfg(
                    prim_path=f"/World/Vials/{cname}_{k}",
                    spawn=sim_utils.CylinderCfg(
                        radius=C.VIAL_RADIUS, height=C.VIAL_HEIGHT,
                        rigid_props=sim_utils.RigidBodyPropertiesCfg(),
                        mass_props=sim_utils.MassPropertiesCfg(mass=C.VIAL_MASS),
                        collision_props=sim_utils.CollisionPropertiesCfg(),
                        visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=rgb, roughness=0.3),
                        physics_material=sim_utils.RigidBodyMaterialCfg(
                            static_friction=1.1, dynamic_friction=1.0
                        ),
                    ),
                    init_state=RigidObjectCfg.InitialStateCfg(pos=self._park_pos(letter, k)),
                )
                self.vials[letter].append(RigidObject(cfg))

        # cameras — names match the real dataset keys exactly
        cam_common = dict(height=C.CAM_HEIGHT, width=C.CAM_WIDTH, data_types=["rgb"],
                          update_period=1.0 / C.FPS)
        self.cam_top = Camera(CameraCfg(
            prim_path="/World/Cams/cam_top",
            spawn=sim_utils.PinholeCameraCfg(focal_length=C.CAM_TOP["focal_length_mm"],
                                             clipping_range=(0.01, 5.0)),
            **cam_common))
        self.cam_side = Camera(CameraCfg(
            prim_path="/World/Cams/cam_side",
            spawn=sim_utils.PinholeCameraCfg(focal_length=C.CAM_SIDE["focal_length_mm"],
                                             clipping_range=(0.01, 5.0)),
            **cam_common))
        self.cam_wrist = Camera(CameraCfg(
            prim_path=f"/World/Robot/{C.CAM_WRIST['parent_link']}/cam_wrist",
            spawn=sim_utils.PinholeCameraCfg(focal_length=C.CAM_WRIST["focal_length_mm"],
                                             clipping_range=(0.005, 5.0)),
            offset=CameraCfg.OffsetCfg(pos=C.CAM_WRIST["offset_pos"],
                                       rot=C.CAM_WRIST["offset_rot_wxyz"], convention="ros"),
            **cam_common))
        self.cameras = {"cam_top": self.cam_top, "cam_side": self.cam_side, "cam_wrist": self.cam_wrist}

    # ── lifecycle ────────────────────────────────────────────────────────────

    def initialize(self):
        """Call once after sim.reset(): resolve joint indices, aim static cams."""
        self._joint_ids = [self.robot.joint_names.index(j) for j in C.JOINT_NAMES]
        limits = self.robot.root_physx_view.get_dof_limits()[0].cpu().numpy()
        g = self._joint_ids[5]
        self._grip_lo, self._grip_hi = float(limits[g, 0]), float(limits[g, 1])
        # per-body-joint (lo, hi) rad, for clamping incoming targets
        self._body_limits = [
            (float(limits[self._joint_ids[i], 0]), float(limits[self._joint_ids[i], 1]))
            for i in range(5)
        ]

        for cam, cfg in ((self.cam_top, C.CAM_TOP), (self.cam_side, C.CAM_SIDE)):
            cam.set_world_poses_from_view(
                eyes=torch.tensor([cfg["eye"]], device=self.device),
                targets=torch.tensor([cfg["target"]], device=self.device),
            )
        self.home()

    def step(self, render: bool = True):
        """One 30 Hz control tick = DECIMATION physics steps + sensor update."""
        for _ in range(C.DECIMATION):
            self.robot.write_data_to_sim()
            self.sim.step(render=False)
            self.robot.update(C.PHYSICS_DT)
        if render:
            self.sim.render()
        for cam in self.cameras.values():
            cam.update(C.DECIMATION * C.PHYSICS_DT)

    # ── robot I/O (degrees + gripper 0..100, like the real bus) ─────────────

    def set_joint_targets(self, action_deg: dict[str, float]):
        """action_deg keys like 'shoulder_pan.pos' (deg), 'gripper.pos' (0..100)."""
        t = self.robot.data.joint_pos_target.clone()
        for i, name in enumerate(C.BODY_JOINTS):
            if f"{name}.pos" in action_deg:
                lo, hi = self._body_limits[i]
                t[0, self._joint_ids[i]] = np.clip(float(action_deg[f"{name}.pos"]) * DEG, lo, hi)
        if "gripper.pos" in action_deg:
            frac = np.clip(float(action_deg["gripper.pos"]) / 100.0, 0.0, 1.0)
            t[0, self._joint_ids[5]] = self._grip_lo + frac * (self._grip_hi - self._grip_lo)
        self.robot.set_joint_position_target(t)

    def get_joint_state(self) -> dict[str, float]:
        """Follower-style observation: '<joint>.pos' in deg, gripper 0..100."""
        q = self.robot.data.joint_pos[0].cpu().numpy()
        obs = {f"{n}.pos": float(q[self._joint_ids[i]] / DEG) for i, n in enumerate(C.BODY_JOINTS)}
        gq = q[self._joint_ids[5]]
        obs["gripper.pos"] = float(100.0 * (gq - self._grip_lo) / (self._grip_hi - self._grip_lo))
        return obs

    def home(self):
        """Teleport-home (sim luxury): joint state AND targets to HOME_POSE."""
        q = self.robot.data.default_joint_pos.clone()
        for i, name in enumerate(C.BODY_JOINTS):
            lo, hi = self._body_limits[i]
            q[0, self._joint_ids[i]] = np.clip(C.HOME_POSE_DEG[name] * DEG, lo, hi)
        q[0, self._joint_ids[5]] = self._grip_lo + (C.HOME_GRIPPER_0100 / 100.0) * (self._grip_hi - self._grip_lo)
        zeros = torch.zeros_like(q)
        self.robot.write_joint_state_to_sim(q, zeros)
        self.robot.set_joint_position_target(q)

    # ── vial placement ───────────────────────────────────────────────────────

    def _park_pos(self, letter: str, k: int):
        i = list(C.VIAL_COLORS).index(letter)
        return (C.VIAL_PARK[0] - 0.05 * k, C.VIAL_PARK[1] + 0.08 * i, C.VIAL_PARK[2])

    def set_scene(self, episode: Episode):
        """Park all vials, then drop the episode's vials into their slots."""
        used: dict[str, int] = {l: 0 for l in C.VIAL_COLORS}
        placements: dict[tuple[str, int], tuple[float, float, float]] = {}
        t_rack, t_slot = episode.target
        # target first, then distractors — no two vials in adjacent slots of a rack
        ordered = sorted(episode.occupied(), key=lambda e: (e[0], e[1]) != (t_rack, t_slot))
        accepted: dict[str, set[int]] = {"left": set(), "right": set()}
        for rack, slot, letter in ordered:
            if (
                getattr(C, "SKIP_ADJACENT_DISTRACTORS", False)
                and (rack, slot) != (t_rack, t_slot)
                and any(abs(slot - s) == 1 for s in accepted[rack])
            ):
                continue  # would sit directly next to an already-placed vial -> parked
            accepted[rack].add(slot)
            k = used[letter]
            if k >= C.VIALS_PER_COLOR:
                raise RuntimeError(f"scene needs >{C.VIALS_PER_COLOR} {letter} vials")
            used[letter] += 1
            x, y, z = C.slot_center(rack, slot)
            placements[(letter, k)] = (x, y, z + C.VIAL_HEIGHT / 2 + 0.002)

        for letter, objs in self.vials.items():
            for k, obj in enumerate(objs):
                pos = placements.get((letter, k), self._park_pos(letter, k))
                state = obj.data.default_root_state.clone()
                state[0, 0:3] = torch.tensor(pos, device=self.device)
                state[0, 3:7] = torch.tensor([1.0, 0, 0, 0], device=self.device)
                state[0, 7:13] = 0.0
                obj.write_root_pose_to_sim(state[:, 0:7])
                obj.write_root_velocity_to_sim(state[:, 7:13])

        # let the vials settle into the wells
        for _ in range(30):
            self.step(render=False)

    def teleport_vial(self, letter: str, k: int, pos):
        obj = self.vials[letter][k]
        state = obj.data.default_root_state.clone()
        state[0, 0:3] = torch.tensor(pos, device=self.device)
        state[0, 3:7] = torch.tensor([1.0, 0, 0, 0], device=self.device)
        state[0, 7:13] = 0.0
        obj.write_root_pose_to_sim(state[:, 0:7])
        obj.write_root_velocity_to_sim(state[:, 7:13])

    def get_vial_positions(self) -> dict[str, list[float]]:
        """World xyz of every vial (debug: verify slot placement survived settling)."""
        out = {}
        for letter, objs in self.vials.items():
            for k, obj in enumerate(objs):
                pos = obj.data.root_pos_w[0].cpu().numpy()
                out[f"{letter}{k}"] = [round(float(v), 3) for v in pos]
        return out

    # ── cameras ──────────────────────────────────────────────────────────────

    def get_images(self) -> dict[str, np.ndarray]:
        """{'cam_top': HxWx3 uint8 RGB, ...} — same keys/shape as the real rig."""
        out = {}
        for name, cam in self.cameras.items():
            rgb = cam.data.output["rgb"][0].cpu().numpy()
            out[name] = rgb[..., :3].astype(np.uint8)  # drop alpha if present
        return out
