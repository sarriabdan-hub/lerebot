# 2. The Vial-Sort Dataset

The core of the work is a **teleoperated demonstration dataset** recorded with LeRobot.
Every timestep logs the three RGB camera streams (a colorized depth channel is stored
alongside), the joint states, and the language instruction. **150 demonstrations**, each a
single atomic pick-and-place, ~23 s (~700 frames) at 30 Hz.

## Task and scenarios
Pick a designated **target** vial from its source slot and place it at a commanded
destination — a rack slot or the discard bin. Targets come in **three colors** (red, cyan,
dark green), **fully crossed** with destinations (every color demonstrated to every
destination). Each scene has **2–4 distractor** vials of other colors, so the policy must
localize the commanded slot in clutter rather than reach for the only object present.

## Constraints (and why)
- **Spacing — no two vials in adjacent slots.** The parallel-jaw gripper needs finger
  clearance on *both* sides; an adjacent vial blocks the grasp and the release. Applied to
  target *and* distractors.
- **Destination clearance — empty slot, both neighbors free.** A release needs room on
  either side; one free neighbor was not enough in practice, so the destination + both
  neighbors are empty, and the target never starts adjacent to its destination.
- **Capacity & stock — ≤3 vials/rack, ≤3 of any color.** Realistically full but feasible;
  the per-color cap matches the physical stock (3 vials/color).
- **Color set — three distinct colors; distractors never the target color.** Denser data
  per color, unambiguous grounding, and the target is the unique vial of its color.
- **Held-out positions.** Sources ∈ {1,3,4,6}; trained destinations ∈ {1,3,6}; slots
  **{2,4,5} held out** to test interpolation to unseen positions.
- **Full crossing.** No color is tied to a fixed slot, so the *instruction* (not a
  color→slot shortcut) must determine the destination.

**Fixed objects are constraints too.** Cameras, racks, and bin are held in fixed positions;
the left/right/slot convention is read off the fixed side-camera image.

**Why a fixed camera.** A fixed viewpoint maps each slot to the *same* image region, so the
policy can reliably ground "slot n." A drifting/moving camera shifts the whole observation
distribution — concretely, when the top camera drifted, a **π0 policy that had worked
stopped working** (inputs moved outside its training distribution). So the rig is kept rigid
and re-anchored to a reference frame; viewpoint stability is a first-class data constraint.

## Prompt design (position grammar, color never named)
Every instruction is composed from independent pools:

| Dimension | Values |
|---|---|
| Verb (6) | Move, Take, Transfer, Bring, Relocate, Carry |
| Object noun (4) | the vial, the tube, the test tube, the sample tube |
| Slot phrasing (5) | position *n*, slot *n*, the *n*th slot, hole *n*, spot *n* |
| Rack phrasing (4) | the left rack, the rack on the left, the left-side rack, the left tube rack |
| Bin phrasing (5) | the bin, the trash, the waste bin, the trash can, the rubbish bin |
| Template (4) | "…from S to D", "…in S to D", "…from S over to D", "…at S to/into D" |

These multiply to ≈ **6 × 4 × (5×4) × (5×4) × 4 ≈ 3.8 × 10⁴** distinct phrasings of a
single rack-to-rack command (≈10⁴ for the bin), sampled deterministically so consecutive
demonstrations of the same command are phrased differently.

**Example prompts:**
- *Move the vial from position 3 of the left rack to slot 6 of the right rack.*
- *Take the tube in slot 3 of the rack on the left to the sixth slot of the right rack.*
- *Transfer the test tube from the third slot of the left-side rack over to hole 6 of the right tube rack.*
- *Bring the sample tube at spot 1 of the left tube rack to position 3 of the right rack.*
- *Relocate the vial from hole 4 of the right rack to the first slot of the left rack.*
- *Move the test tube from position 4 of the right rack to the trash can.*

## Recording, representation, and fields
- **Recording:** short runs sharing one command, deterministic seeded sheet, balanced
  (color, destination) coverage, home pose + reset between episodes.
- **Representation:** end-effector frame — 7-D EE pose (position, orientation, gripper) via
  forward kinematics from the URDF.
- **Data fields:** 3 RGB images (top/wrist/side) + colorized depth, `observation.state`
  (7-D), `action` (7-D), the task string, episode/frame indices.

*Figures:* `teleop_dataset.png`, `scene_example.drawio.png`.
