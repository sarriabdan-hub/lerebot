# 5. Experiments and Results

## Deployment
A chosen checkpoint is served on the Jetson by an inference server that exposes a
**browser control panel** with the three live camera feeds and Home/Execute
controls. Before every command the arm **homes to the start pose of the
demonstrations**; a mismatch here produced an out-of-distribution transient (the
arm flailed before recovering), corrected by setting the home pose directly from
the recorded data.

## Checkpoint study
| Checkpoint | Follows command | Grasps | Completes rack placement |
|---|---|---|---|
| 8k | no | — | — |
| **12k** | **yes** | **yes** | **yes** |
| 16k | yes | no | no |

- **8k** — under-trained language grounding; does not follow the command.
- **12k** — the operating point we deploy: follows commands, grasps, completes placements.
- **16k** — over-fit; loses the grasp.

This is the expected data-density / over-fitting curve.

## Command following
Verified by holding the scene fixed and **changing only the destination clause** —
the arm then proceeds to different targets accordingly. The deployed policy
follows the commanded source-to-destination move reliably.

## Grasping and placement
- **Grasping** is reliable at the **central slot**; the two **outermost slots
  (1 and 6)** lie at the arm's reach extremes and are harder.
- **Rack-to-rack placement completes** end to end — the policy lowers the vial into
  the target slot and releases it: a **complete autonomous sort**.

## Bin placement
For discard commands the arm **carries the vial over the bin but does not release
it**. This persists across the 8k/12k/16k checkpoints and is therefore **not a
training-duration effect**; it traces to **demonstration inconsistency** (the bin
was demonstrated as varied throws, which imitation learning averages into a
non-committal hover), compounded by the bin's location at the workspace extreme.
The implication is that a small set of **consistent** bin-release demonstrations,
not a different checkpoint, addresses the behavior.

## Discussion
Grasp and placement behavior is consistent with the known relationship between
demonstration count and success for SO-101-class manipulators: reliability at a
given source/destination scales with the density of demonstrations covering it —
explaining both the strong central-slot behavior and the weaker extremes. The
checkpoint study reproduces the standard trade-off between under-fit language
grounding and over-fit motor behavior, with a clear intermediate optimum.

*Figures:* `dashboard.png`, `rack_sort_sequence.png`, `bin_hover.png`.
